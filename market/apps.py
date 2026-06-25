"""Market app configuration.

Two responsibilities run at startup:
  1. Put SQLite into WAL mode so the engine thread can write while web
     requests read concurrently.
  2. Auto-launch the simulation engine under ``runserver`` (in the worker
     process only, never the autoreload watcher).
"""
import os
import sys

from django.apps import AppConfig
from django.conf import settings
from django.db.backends.signals import connection_created


def _enable_sqlite_wal(sender, connection, **kwargs):
    if connection.vendor != "sqlite":
        return
    cursor = connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.execute("PRAGMA busy_timeout=5000;")


class MarketConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "market"
    verbose_name = "Market Data & Simulation"

    def ready(self):
        connection_created.connect(_enable_sqlite_wal)

        engine_cfg = getattr(settings, "MARKET_ENGINE", {})
        if not engine_cfg.get("AUTOSTART", False):
            return

        # Only run inside the live runserver worker process.
        is_runserver = "runserver" in sys.argv
        is_worker = os.environ.get("RUN_MAIN") == "true"
        if is_runserver and is_worker:
            from . import engine

            engine.start()
