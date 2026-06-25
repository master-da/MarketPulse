from django.apps import AppConfig


class TradingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "trading"
    verbose_name = "Trading & Portfolios"

    def ready(self):
        from . import signals  # noqa: F401  (register signal handlers)
