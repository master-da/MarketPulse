"""DRF serializers for the trading domain."""
from rest_framework import serializers

from .models import Holding, Order, Trade


class HoldingSerializer(serializers.ModelSerializer):
    symbol = serializers.CharField(source="instrument.symbol", read_only=True)
    name = serializers.CharField(source="instrument.name", read_only=True)
    last_price = serializers.DecimalField(
        source="instrument.last_price", max_digits=12, decimal_places=2, read_only=True
    )
    market_value = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    cost_basis = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    unrealized_pnl = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    unrealized_pnl_pct = serializers.FloatField(read_only=True)

    class Meta:
        model = Holding
        fields = [
            "symbol", "name", "quantity", "avg_cost", "last_price",
            "market_value", "cost_basis", "unrealized_pnl", "unrealized_pnl_pct",
        ]


class TradeSerializer(serializers.ModelSerializer):
    symbol = serializers.CharField(source="instrument.symbol", read_only=True)

    class Meta:
        model = Trade
        fields = ["id", "symbol", "side", "quantity", "price", "value", "timestamp"]


class OrderSerializer(serializers.ModelSerializer):
    symbol = serializers.CharField(source="instrument.symbol", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id", "symbol", "side", "order_type", "quantity", "limit_price",
            "status", "filled_quantity", "avg_fill_price", "reject_reason",
            "created_at",
        ]


class OrderCreateSerializer(serializers.Serializer):
    """Incoming order payload (validated, then handed to the service layer)."""

    symbol = serializers.CharField(max_length=12)
    side = serializers.ChoiceField(choices=["BUY", "SELL"])
    order_type = serializers.ChoiceField(choices=["MARKET", "LIMIT"], default="MARKET")
    quantity = serializers.IntegerField(min_value=1)
    limit_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
