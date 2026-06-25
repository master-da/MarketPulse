from django.contrib import admin

from .models import Holding, Order, Portfolio, Trade


class HoldingInline(admin.TabularInline):
    model = Holding
    extra = 0
    readonly_fields = ("market_value", "unrealized_pnl")


@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    list_display = ("user", "cash_balance", "realized_pnl", "is_bot", "created_at")
    list_filter = ("is_bot",)
    search_fields = ("user__username",)
    inlines = [HoldingInline]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id", "portfolio", "side", "order_type", "instrument",
        "quantity", "status", "avg_fill_price", "created_at",
    )
    list_filter = ("status", "side", "order_type")
    search_fields = ("portfolio__user__username", "instrument__symbol")


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = ("id", "portfolio", "side", "instrument", "quantity", "price", "value", "timestamp")
    list_filter = ("side", "instrument")
    date_hierarchy = "timestamp"
