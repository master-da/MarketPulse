"""Trading domain: portfolios, holdings, orders, and executed trades."""
from decimal import Decimal

from django.conf import settings
from django.db import models

from market.models import Instrument


class Side(models.TextChoices):
    BUY = "BUY", "Buy"
    SELL = "SELL", "Sell"


class OrderType(models.TextChoices):
    MARKET = "MARKET", "Market"
    LIMIT = "LIMIT", "Limit"


class OrderStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    FILLED = "FILLED", "Filled"
    CANCELLED = "CANCELLED", "Cancelled"
    REJECTED = "REJECTED", "Rejected"


class Portfolio(models.Model):
    """A trader's account: a cash balance plus a set of holdings."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="portfolio"
    )
    cash_balance = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))
    realized_pnl = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))
    is_bot = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Portfolio<{self.user.username}>"

    @property
    def holdings_value(self) -> Decimal:
        total = Decimal("0")
        for holding in self.holdings.select_related("instrument"):
            total += holding.market_value
        return total

    @property
    def equity(self) -> Decimal:
        """Total account value = cash + marked-to-market holdings."""
        return self.cash_balance + self.holdings_value


class Holding(models.Model):
    """A position in one instrument within a portfolio."""

    portfolio = models.ForeignKey(
        Portfolio, related_name="holdings", on_delete=models.CASCADE
    )
    instrument = models.ForeignKey(Instrument, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=0)
    avg_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["portfolio", "instrument"], name="unique_holding"
            )
        ]
        ordering = ["instrument__symbol"]

    def __str__(self):
        return f"{self.quantity} {self.instrument.symbol} @ {self.avg_cost}"

    @property
    def market_value(self) -> Decimal:
        return self.instrument.last_price * self.quantity

    @property
    def cost_basis(self) -> Decimal:
        return self.avg_cost * self.quantity

    @property
    def unrealized_pnl(self) -> Decimal:
        return self.market_value - self.cost_basis

    @property
    def unrealized_pnl_pct(self) -> float:
        if not self.cost_basis:
            return 0.0
        return float(self.unrealized_pnl / self.cost_basis * 100)


class Order(models.Model):
    """An instruction to buy or sell. Market orders fill immediately;
    limit orders rest until the simulated price crosses their limit."""

    portfolio = models.ForeignKey(
        Portfolio, related_name="orders", on_delete=models.CASCADE
    )
    instrument = models.ForeignKey(Instrument, on_delete=models.CASCADE)
    side = models.CharField(max_length=4, choices=Side.choices)
    order_type = models.CharField(max_length=6, choices=OrderType.choices)
    quantity = models.PositiveIntegerField()
    limit_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    status = models.CharField(
        max_length=10, choices=OrderStatus.choices, default=OrderStatus.OPEN
    )
    filled_quantity = models.PositiveIntegerField(default=0)
    avg_fill_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    reject_reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "instrument"])]

    def __str__(self):
        return f"{self.side} {self.quantity} {self.instrument.symbol} [{self.status}]"


class Trade(models.Model):
    """An executed fill. ``portfolio`` is denormalized for fast leaderboards."""

    order = models.ForeignKey(Order, related_name="trades", on_delete=models.CASCADE)
    portfolio = models.ForeignKey(
        Portfolio, related_name="trades", on_delete=models.CASCADE
    )
    instrument = models.ForeignKey(Instrument, on_delete=models.CASCADE)
    side = models.CharField(max_length=4, choices=Side.choices)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=12, decimal_places=2)
    value = models.DecimalField(max_digits=16, decimal_places=2)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [models.Index(fields=["portfolio", "-timestamp"])]

    def __str__(self):
        return f"{self.side} {self.quantity} {self.instrument.symbol} @ {self.price}"
