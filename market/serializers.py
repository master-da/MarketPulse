"""DRF serializers for market data."""
from rest_framework import serializers

from .models import Instrument, PriceTick


class PriceTickSerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceTick
        fields = ["price", "volume", "timestamp"]


class InstrumentSerializer(serializers.ModelSerializer):
    change = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    change_pct = serializers.FloatField(read_only=True)
    is_up = serializers.BooleanField(read_only=True)

    class Meta:
        model = Instrument
        fields = [
            "symbol",
            "name",
            "sector",
            "last_price",
            "previous_close",
            "day_high",
            "day_low",
            "change",
            "change_pct",
            "is_up",
            "volatility",
        ]
