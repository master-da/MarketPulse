"""Read-only market data API + engine status."""
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import engine
from .models import Instrument
from .serializers import InstrumentSerializer, PriceTickSerializer


class InstrumentViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve instruments and fetch per-symbol price history."""

    serializer_class = InstrumentSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "symbol"
    lookup_value_regex = "[A-Za-z0-9.]+"

    def get_queryset(self):
        return Instrument.objects.active()

    @action(detail=True, methods=["get"])
    def history(self, request, symbol=None):
        """Recent price ticks for a single instrument (oldest -> newest)."""
        instrument = self.get_object()
        try:
            limit = min(int(request.query_params.get("limit", 120)), 600)
        except (TypeError, ValueError):
            limit = 120
        ticks = instrument.ticks.all()[:limit]  # already -timestamp ordered
        data = PriceTickSerializer(reversed(list(ticks)), many=True).data
        return Response({"symbol": instrument.symbol, "ticks": data})


class MarketStatusView(APIView):
    """Live engine heartbeat: tick count, interval, uptime."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(engine.status())
