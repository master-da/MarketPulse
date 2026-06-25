"""Trading API: portfolio, orders, trades, leaderboard."""
from decimal import Decimal

from django.conf import settings
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Order, Portfolio, Trade
from .serializers import (
    HoldingSerializer,
    OrderCreateSerializer,
    OrderSerializer,
    TradeSerializer,
)
from .services import OrderError, leaderboard_data, place_order, cancel_order


def get_portfolio(user) -> Portfolio:
    starting = Decimal(str(settings.MARKET_ENGINE.get("STARTING_CASH", 100_000)))
    portfolio, _ = Portfolio.objects.get_or_create(
        user=user, defaults={"cash_balance": starting}
    )
    return portfolio


class PortfolioView(APIView):
    """Snapshot of the current user's account: cash, equity, P&L, holdings."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        portfolio = (
            Portfolio.objects.select_related("user")
            .prefetch_related("holdings__instrument")
            .get(pk=get_portfolio(request.user).pk)
        )
        starting = Decimal(str(settings.MARKET_ENGINE.get("STARTING_CASH", 100_000)))
        holdings_value = portfolio.holdings_value
        equity = portfolio.cash_balance + holdings_value
        unrealized = sum(
            (h.unrealized_pnl for h in portfolio.holdings.all()), Decimal("0")
        )
        return Response(
            {
                "username": portfolio.user.username,
                "cash_balance": portfolio.cash_balance,
                "holdings_value": holdings_value,
                "equity": equity,
                "starting_cash": starting,
                "realized_pnl": portfolio.realized_pnl,
                "unrealized_pnl": unrealized,
                "total_return_pct": float((equity - starting) / starting * 100)
                if starting else 0.0,
                "holdings": HoldingSerializer(
                    portfolio.holdings.select_related("instrument"), many=True
                ).data,
            }
        )


class OrderViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """List the user's orders and submit new ones."""

    permission_classes = [IsAuthenticated]
    serializer_class = OrderSerializer

    def get_queryset(self):
        return (
            Order.objects.filter(portfolio__user=self.request.user)
            .select_related("instrument")
        )

    def create(self, request, *args, **kwargs):
        payload = OrderCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        try:
            order = place_order(
                get_portfolio(request.user),
                symbol=data["symbol"],
                side=data["side"],
                order_type=data.get("order_type", "MARKET"),
                quantity=data["quantity"],
                limit_price=data.get("limit_price"),
            )
        except OrderError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = self.get_object()
        try:
            cancel_order(order)
        except OrderError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrderSerializer(order).data)


class TradeViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """The current user's executed trades (the trade tape)."""

    permission_classes = [IsAuthenticated]
    serializer_class = TradeSerializer

    def get_queryset(self):
        return (
            Trade.objects.filter(portfolio__user=self.request.user)
            .select_related("instrument")
        )


class LeaderboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"leaderboard": leaderboard_data()})
