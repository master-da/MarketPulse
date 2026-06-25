"""The MarketPulse simulation engine.

A daemon thread advances every active instrument's price on a fixed
interval using a Gaussian random walk, persists a :class:`PriceTick`,
drives limit-order matching, nudges the bot traders, and prunes old
history. It is intentionally self-contained so the whole demo runs from
``manage.py runserver`` with no external broker, queue, or scheduler.
"""
import logging
import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.core.cache import cache
from django.db import close_old_connections, connection
from django.utils import timezone

from .models import Instrument, PriceTick
from .utils import to_money

logger = logging.getLogger("marketpulse.engine")

SNAPSHOT_CACHE_KEY = "market:snapshot"
_PRUNE_EVERY = 25  # prune history every N ticks


@dataclass
class EngineState:
    running: bool = False
    tick_count: int = 0
    started_at: datetime | None = None
    last_tick_at: datetime | None = None
    tick_interval: float = 1.5
    lock: threading.Lock = field(default_factory=threading.Lock)


STATE = EngineState()
_thread: threading.Thread | None = None
_stop_event = threading.Event()


def _config():
    return getattr(settings, "MARKET_ENGINE", {})


def _next_price(last: float, drift: float, volatility: float) -> float:
    """One step of a Gaussian random walk with a small mean-reversion pull
    that keeps prices from wandering off to zero or infinity."""
    shock = random.gauss(0.0, 1.0)
    ret = drift + volatility * shock
    # Rare "news" spikes for visual interest.
    if random.random() < 0.012:
        ret += random.choice([-1, 1]) * volatility * random.uniform(3, 6)
    new_price = last * (1.0 + ret)
    return max(0.25, new_price)


def _advance_tick() -> int:
    """Advance every active instrument by one tick. Returns # updated."""
    instruments = list(Instrument.objects.active())
    if not instruments:
        return 0

    now = timezone.now()
    ticks: list[PriceTick] = []

    for inst in instruments:
        last = float(inst.last_price)
        new_price = _next_price(last, inst.drift, inst.volatility)
        money = to_money(new_price)

        inst.last_price = money
        if money > inst.day_high:
            inst.day_high = money
        if money < inst.day_low or inst.day_low == 0:
            inst.day_low = money

        magnitude = abs(new_price - last) / max(last, 1.0)
        volume = int(50 + magnitude * 40_000 * random.uniform(0.5, 1.5))
        ticks.append(PriceTick(instrument=inst, price=money, volume=volume, timestamp=now))

    PriceTick.objects.bulk_create(ticks)
    Instrument.objects.bulk_update(
        instruments, ["last_price", "day_high", "day_low"]
    )

    _write_snapshot(instruments, now)
    return len(instruments)


def _write_snapshot(instruments, now) -> None:
    """Cache a compact market snapshot for the status endpoint / ticker."""
    snapshot = {
        "tick": STATE.tick_count,
        "as_of": now.isoformat(),
        "instruments": [
            {
                "symbol": inst.symbol,
                "name": inst.name,
                "price": float(inst.last_price),
                "change_pct": round(inst.change_pct, 2),
            }
            for inst in instruments
        ],
    }
    cache.set(SNAPSHOT_CACHE_KEY, snapshot, timeout=30)


def _prune_history() -> None:
    keep = _config().get("MAX_HISTORY_TICKS", 600)
    for inst_id in Instrument.objects.values_list("id", flat=True):
        keep_ids = list(
            PriceTick.objects.filter(instrument_id=inst_id)
            .order_by("-timestamp")
            .values_list("id", flat=True)[:keep]
        )
        if len(keep_ids) >= keep:
            PriceTick.objects.filter(instrument_id=inst_id).exclude(
                id__in=keep_ids
            ).delete()


def _run_loop() -> None:
    cfg = _config()
    interval = float(cfg.get("TICK_INTERVAL", 1.5))
    STATE.tick_interval = interval
    STATE.running = True
    STATE.started_at = timezone.now()
    logger.info("Market engine started (interval=%.2fs)", interval)

    # Lazy imports to avoid app-loading circular dependencies.
    from trading.services import match_open_orders, run_bot_traders

    while not _stop_event.is_set():
        start = time.monotonic()
        try:
            updated = _advance_tick()
            if updated:
                STATE.tick_count += 1
                STATE.last_tick_at = timezone.now()
                match_open_orders()
                run_bot_traders()
                if STATE.tick_count % _PRUNE_EVERY == 0:
                    _prune_history()
        except Exception:  # keep the loop alive across transient DB hiccups
            logger.exception("Market tick failed; continuing")
            close_old_connections()

        elapsed = time.monotonic() - start
        _stop_event.wait(max(0.05, interval - elapsed))

    STATE.running = False
    connection.close()
    logger.info("Market engine stopped after %d ticks", STATE.tick_count)


def start(force: bool = False) -> bool:
    """Start the engine thread if it isn't already running."""
    global _thread
    with STATE.lock:
        if STATE.running and not force:
            return False
        if _thread and _thread.is_alive():
            return False
        _stop_event.clear()
        _thread = threading.Thread(
            target=_run_loop, name="market-engine", daemon=True
        )
        _thread.start()
        return True


def stop() -> None:
    _stop_event.set()


def status() -> dict:
    return {
        "running": STATE.running,
        "tick_count": STATE.tick_count,
        "tick_interval": STATE.tick_interval,
        "started_at": STATE.started_at.isoformat() if STATE.started_at else None,
        "last_tick_at": STATE.last_tick_at.isoformat() if STATE.last_tick_at else None,
        "server_time": datetime.now(dt_timezone.utc).isoformat(),
    }
