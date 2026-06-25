"""Market data models: tradeable instruments and their price history."""
from decimal import Decimal

from django.db import models
from django.utils import timezone


class InstrumentQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class Instrument(models.Model):
    """A tradeable security with a live, simulated price."""

    symbol = models.CharField(max_length=12, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    sector = models.CharField(max_length=60, blank=True)

    # Pricing
    initial_price = models.DecimalField(max_digits=12, decimal_places=2)
    last_price = models.DecimalField(max_digits=12, decimal_places=2)
    previous_close = models.DecimalField(max_digits=12, decimal_places=2)
    day_high = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    day_low = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))

    # Simulation parameters (per-tick, expressed as fractions)
    volatility = models.FloatField(default=0.01, help_text="Per-tick stdev of returns")
    drift = models.FloatField(default=0.0, help_text="Per-tick mean of returns")

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = InstrumentQuerySet.as_manager()

    class Meta:
        ordering = ["symbol"]

    def __str__(self):
        return f"{self.symbol} ({self.name})"

    @property
    def change(self) -> Decimal:
        return self.last_price - self.previous_close

    @property
    def change_pct(self) -> float:
        if not self.previous_close:
            return 0.0
        return float(self.change / self.previous_close * 100)

    @property
    def is_up(self) -> bool:
        return self.last_price >= self.previous_close


class PriceTick(models.Model):
    """A single observed price point for an instrument."""

    instrument = models.ForeignKey(
        Instrument, related_name="ticks", on_delete=models.CASCADE
    )
    price = models.DecimalField(max_digits=12, decimal_places=2)
    volume = models.PositiveIntegerField(default=0)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["instrument", "-timestamp"]),
        ]

    def __str__(self):
        return f"{self.instrument.symbol} @ {self.price} ({self.timestamp:%H:%M:%S})"
