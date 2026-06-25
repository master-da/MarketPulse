from django.contrib import admin

from .models import Instrument, PriceTick


@admin.register(Instrument)
class InstrumentAdmin(admin.ModelAdmin):
    list_display = (
        "symbol", "name", "sector", "last_price",
        "previous_close", "change_pct", "is_active",
    )
    list_filter = ("sector", "is_active")
    search_fields = ("symbol", "name")
    readonly_fields = ("created_at",)

    @admin.display(description="Change %")
    def change_pct(self, obj):
        return f"{obj.change_pct:+.2f}%"


@admin.register(PriceTick)
class PriceTickAdmin(admin.ModelAdmin):
    list_display = ("instrument", "price", "volume", "timestamp")
    list_filter = ("instrument",)
    date_hierarchy = "timestamp"
