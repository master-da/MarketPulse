"""The order-execution engine.

All trade mutations funnel through here and are serialized with a single
process-wide re-entrant lock, so the background market thread (limit-order
matching, bot activity) and human web requests can never interleave a
half-applied fill. Each fill is also wrapped in a DB transaction.
"""
import logging
import random
import threading
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.db import transaction

from market.models import Instrument

from .models import Holding, Order, OrderStatus, OrderType, Portfolio, Side, Trade

logger = logging.getLogger("marketpulse.trading")

# Serializes every balance/holding mutation across all threads.
_trade_lock = threading.RLock()

LEADERBOARD_CACHE_KEY = "leaderboard"


class OrderError(Exception):
    """Raised for invalid order requests (insufficient funds, bad qty, ...)."""


def _starting_cash() -> Decimal:
    return Decimal(str(settings.MARKET_ENGINE.get("STARTING_CASH", 100_000)))


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------
def place_order(
    portfolio: Portfolio,
    *,
    symbol: str,
    side: str,
    order_type: str,
    quantity: int,
    limit_price=None,
) -> Order:
    """Validate and submit an order. Market orders fill immediately; valid
    limit orders rest as OPEN (and fill instantly if already in the money)."""
    side = side.upper()
    order_type = order_type.upper()

    if side not in Side.values:
        raise OrderError(f"Invalid side: {side!r}")
    if order_type not in OrderType.values:
        raise OrderError(f"Invalid order type: {order_type!r}")
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        raise OrderError("Quantity must be a whole number.")
    if quantity <= 0:
        raise OrderError("Quantity must be greater than zero.")

    if order_type == OrderType.LIMIT:
        if limit_price in (None, ""):
            raise OrderError("Limit orders require a limit price.")
        limit_price = Decimal(str(limit_price))
        if limit_price <= 0:
            raise OrderError("Limit price must be positive.")

    with _trade_lock, transaction.atomic():
        try:
            instrument = Instrument.objects.active().get(symbol=symbol.upper())
        except Instrument.DoesNotExist:
            raise OrderError(f"Unknown instrument: {symbol!r}")

        portfolio = Portfolio.objects.select_for_update().get(pk=portfolio.pk)

        order = Order(
            portfolio=portfolio,
            instrument=instrument,
            side=side,
            order_type=order_type,
            quantity=quantity,
            limit_price=limit_price if order_type == OrderType.LIMIT else None,
        )

        if order_type == OrderType.MARKET:
            _ensure_executable(portfolio, instrument, side, quantity, instrument.last_price)
            order.save()
            _apply_fill(order, instrument.last_price)
        else:
            order.save()  # rests OPEN
            if _limit_crosses(order, instrument.last_price):
                _try_fill_limit(order)

    cache.delete(LEADERBOARD_CACHE_KEY)
    return order


def cancel_order(order: Order) -> Order:
    with _trade_lock, transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.status != OrderStatus.OPEN:
            raise OrderError("Only open orders can be cancelled.")
        order.status = OrderStatus.CANCELLED
        order.save(update_fields=["status", "updated_at"])
    return order


# --------------------------------------------------------------------------
# Engine hooks (called once per market tick)
# --------------------------------------------------------------------------
def match_open_orders() -> int:
    """Fill any resting limit order whose price has been crossed."""
    filled = 0
    with _trade_lock:
        open_orders = (
            Order.objects.filter(status=OrderStatus.OPEN, order_type=OrderType.LIMIT)
            .select_related("instrument", "portfolio")
        )
        for order in open_orders:
            if _limit_crosses(order, order.instrument.last_price):
                with transaction.atomic():
                    if _try_fill_limit(order):
                        filled += 1
    if filled:
        cache.delete(LEADERBOARD_CACHE_KEY)
    return filled


def run_bot_traders() -> None:
    """Give bot portfolios a small random chance to trade each tick so the
    leaderboard and trade tape stay alive during a demo."""
    with _trade_lock:
        bots = list(Portfolio.objects.filter(is_bot=True))
        instruments = list(Instrument.objects.active())
        if not bots or not instruments:
            return

        for bot in bots:
            if random.random() > 0.30:
                continue
            instrument = random.choice(instruments)
            side = random.choice([Side.BUY, Side.SELL])
            qty = random.randint(5, 60)
            try:
                place_order(
                    bot,
                    symbol=instrument.symbol,
                    side=side,
                    order_type=OrderType.MARKET,
                    quantity=qty,
                )
            except OrderError:
                pass  # bot was broke or had no shares; skip silently


# --------------------------------------------------------------------------
# Internals
# --------------------------------------------------------------------------
def _limit_crosses(order: Order, price: Decimal) -> bool:
    if order.side == Side.BUY:
        return price <= order.limit_price
    return price >= order.limit_price


def _ensure_executable(portfolio, instrument, side, quantity, price) -> None:
    if side == Side.BUY:
        cost = price * quantity
        if portfolio.cash_balance < cost:
            raise OrderError(
                f"Insufficient cash: need ${cost:,.2f}, have ${portfolio.cash_balance:,.2f}."
            )
    else:
        held = (
            Holding.objects.filter(portfolio=portfolio, instrument=instrument)
            .values_list("quantity", flat=True)
            .first()
        ) or 0
        if held < quantity:
            raise OrderError(f"Insufficient shares: need {quantity}, have {held}.")


def _try_fill_limit(order: Order) -> bool:
    """Fill a resting limit order if funds/shares allow, else reject it."""
    price = order.instrument.last_price
    try:
        _ensure_executable(
            order.portfolio, order.instrument, order.side, order.quantity, price
        )
    except OrderError as exc:
        order.status = OrderStatus.REJECTED
        order.reject_reason = str(exc)
        order.save(update_fields=["status", "reject_reason", "updated_at"])
        return False
    _apply_fill(order, price)
    return True


def _apply_fill(order: Order, price: Decimal) -> None:
    """Apply a full fill: move cash, adjust the holding, record the trade."""
    qty = order.quantity
    value = price * qty
    portfolio = order.portfolio

    holding, _ = Holding.objects.get_or_create(
        portfolio=portfolio, instrument=order.instrument
    )

    if order.side == Side.BUY:
        portfolio.cash_balance -= value
        new_qty = holding.quantity + qty
        # Weighted-average cost basis.
        holding.avg_cost = (holding.cost_basis + value) / new_qty
        holding.quantity = new_qty
        holding.save()
    else:  # SELL
        realized = (price - holding.avg_cost) * qty
        portfolio.realized_pnl += realized
        portfolio.cash_balance += value
        holding.quantity -= qty
        if holding.quantity <= 0:
            holding.delete()
        else:
            holding.save()

    portfolio.save(update_fields=["cash_balance", "realized_pnl"])

    order.status = OrderStatus.FILLED
    order.filled_quantity = qty
    order.avg_fill_price = price
    order.save(update_fields=["status", "filled_quantity", "avg_fill_price", "updated_at"])

    Trade.objects.create(
        order=order,
        portfolio=portfolio,
        instrument=order.instrument,
        side=order.side,
        quantity=qty,
        price=price,
        value=value,
    )


# --------------------------------------------------------------------------
# Analytics
# --------------------------------------------------------------------------
def compute_equity(portfolio: Portfolio) -> Decimal:
    """Equity using already-prefetched holdings (avoids N+1 in leaderboards)."""
    total = portfolio.cash_balance
    for holding in portfolio.holdings.all():
        total += holding.instrument.last_price * holding.quantity
    return total


def leaderboard_data(limit: int = 15) -> list[dict]:
    cached = cache.get(LEADERBOARD_CACHE_KEY)
    if cached is not None:
        return cached[:limit]

    start = _starting_cash()
    rows = []
    portfolios = Portfolio.objects.select_related("user").prefetch_related(
        "holdings__instrument"
    )
    for p in portfolios:
        equity = compute_equity(p)
        pnl = equity - start
        rows.append(
            {
                "username": p.user.username,
                "is_bot": p.is_bot,
                "equity": float(equity),
                "pnl": float(pnl),
                "return_pct": float(pnl / start * 100) if start else 0.0,
            }
        )
    rows.sort(key=lambda r: r["equity"], reverse=True)
    for i, row in enumerate(rows, start=1):
        row["rank"] = i

    cache.set(LEADERBOARD_CACHE_KEY, rows, timeout=3)
    return rows[:limit]
