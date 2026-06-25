"""Run the market simulation engine in the foreground.

Useful when AUTOSTART is disabled or when serving via gunicorn/uvicorn
where the in-process autostart hook does not fire. Ctrl-C to stop.
"""
from django.core.management.base import BaseCommand

from market import engine


class Command(BaseCommand):
    help = "Run the market simulation engine in the foreground (blocking)."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting market engine... (Ctrl-C to stop)"))
        engine.start(force=True)
        try:
            while True:
                import time

                time.sleep(1)
        except KeyboardInterrupt:
            engine.stop()
            self.stdout.write(self.style.WARNING("\nMarket engine stopped."))
