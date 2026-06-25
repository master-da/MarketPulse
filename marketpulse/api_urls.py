"""Aggregated REST API routing for MarketPulse."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from market.api import InstrumentViewSet, MarketStatusView
from trading.api import (
    LeaderboardView,
    OrderViewSet,
    PortfolioView,
    TradeViewSet,
)

router = DefaultRouter()
router.register("instruments", InstrumentViewSet, basename="instrument")
router.register("orders", OrderViewSet, basename="order")
router.register("trades", TradeViewSet, basename="trade")

urlpatterns = [
    path("", include(router.urls)),
    path("market/status/", MarketStatusView.as_view(), name="market-status"),
    path("portfolio/", PortfolioView.as_view(), name="portfolio"),
    path("leaderboard/", LeaderboardView.as_view(), name="leaderboard"),
]
