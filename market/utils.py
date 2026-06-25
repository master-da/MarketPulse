"""Shared money helpers.

Prices and cash are stored as ``Decimal`` for correctness, but the
simulation does its random-walk math in ``float``. These helpers are the
single conversion boundary between the two worlds.
"""
from decimal import ROUND_HALF_UP, Decimal

CENTS = Decimal("0.01")


def to_money(value) -> Decimal:
    """Quantize any numeric value to 2 decimal places as a ``Decimal``."""
    return Decimal(str(value)).quantize(CENTS, rounding=ROUND_HALF_UP)
