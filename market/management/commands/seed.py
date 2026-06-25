"""Seed the simulator with instruments, price history, a demo user, and bots.

Usage:
    python manage.py seed            # idempotent top-up
    python manage.py seed --reset    # wipe trading/market data and reseed
"""
import random
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from market.models import Instrument, PriceTick
from market.utils import to_money
from trading.models import Holding, Order, Portfolio, Trade
from trading.services import place_order

INSTRUMENTS = [
    # symbol, name, sector, price, volatility, drift
    ("AAPL",  "Apple Inc.",            "Technology",     190.0,  0.007,  0.0003),
    ("MSFT",  "Microsoft Corp.",       "Technology",     420.0,  0.006,  0.0003),
    ("NVDA",  "NVIDIA Corp.",          "Semiconductors", 120.0,  0.012,  0.0006),
    ("TSLA",  "Tesla Inc.",            "Automotive",     250.0,  0.015,  0.0001),
    ("AMZN",  "Amazon.com Inc.",       "Consumer",       185.0,  0.008,  0.0003),
    ("GOOGL", "Alphabet Inc.",         "Technology",     175.0,  0.007,  0.0002),
    ("META",  "Meta Platforms Inc.",   "Technology",     500.0,  0.009,  0.0003),
    ("JPM",   "JPMorgan Chase & Co.",  "Financials",     200.0,  0.005,  0.0001),
    ("XOM",   "Exxon Mobil Corp.",     "Energy",         110.0,  0.006, -0.0001),
    ("DIS",   "The Walt Disney Co.",   "Media",          100.0,  0.008,  0.0000),
    ("BTC-X", "BitMint Token",         "Crypto",       64000.0,  0.022,  0.0008),
    ("GLD",   "Gold Bullion ETF",      "Commodities",    215.0,  0.003,  0.0001),
]

BOTS = [
    "QuantWolf", "AlgoApe", "MeanReverter", "MomentumMax",
    "DeltaHedge", "VolHarvester", "DiamondHands",
]

HISTORY_TICKS = 90


class Command(BaseCommand):
    help = "Seed instruments, price history, a demo account, and bot traders."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset", action="store_true",
            help="Delete existing market/trading data before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            self.stdout.write(self.style.WARNING("Resetting market & trading data..."))
            Trade.objects.all().delete()
            Order.objects.all().delete()
            Holding.objects.all().delete()
            PriceTick.objects.all().delete()
            Portfolio.objects.all().delete()
            Instrument.objects.all().delete()

        self._seed_instruments()
        self._seed_demo_user()
        self._seed_bots()
        self._seed_superuser()

        self.stdout.write(self.style.SUCCESS("\nSeed complete."))
        self.stdout.write("  Demo login : demo / demo12345")
        self.stdout.write("  Admin login: admin / admin12345  (/admin)")

    # ------------------------------------------------------------------
    def _seed_instruments(self):
        interval = float(settings.MARKET_ENGINE.get("TICK_INTERVAL", 1.5))
        now = timezone.now()
        created = 0
        for symbol, name, sector, price, vol, drift in INSTRUMENTS:
            inst, was_created = Instrument.objects.get_or_create(
                symbol=symbol,
                defaults={
                    "name": name,
                    "sector": sector,
                    "initial_price": to_money(price),
                    "last_price": to_money(price),
                    "previous_close": to_money(price),
                    "day_high": to_money(price),
                    "day_low": to_money(price),
                    "volatility": vol,
                    "drift": drift,
                },
            )
            if not was_created:
                continue
            created += 1

            # Backfill a believable price history so charts render on load.
            p = price
            highs, lows = p, p
            ticks = []
            for i in range(HISTORY_TICKS):
                shock = random.gauss(0.0, 1.0)
                p = max(0.25, p * (1.0 + drift + vol * shock))
                highs, lows = max(highs, p), min(lows, p)
                ts = now - timedelta(seconds=(HISTORY_TICKS - i) * interval)
                ticks.append(
                    PriceTick(
                        instrument=inst,
                        price=to_money(p),
                        volume=random.randint(100, 5000),
                        timestamp=ts,
                    )
                )
            PriceTick.objects.bulk_create(ticks)
            inst.previous_close = to_money(price)
            inst.last_price = to_money(p)
            inst.day_high = to_money(highs)
            inst.day_low = to_money(lows)
            inst.save()

        self.stdout.write(f"  Instruments: {created} created, "
                          f"{Instrument.objects.count()} total.")

    def _portfolio_for(self, username, *, is_bot=False, password=None):
        start = Decimal(str(settings.MARKET_ENGINE.get("STARTING_CASH", 100_000)))
        user, created = User.objects.get_or_create(username=username)
        if created and password:
            user.set_password(password)
            user.save()
        portfolio, _ = Portfolio.objects.get_or_create(
            user=user, defaults={"cash_balance": start, "is_bot": is_bot}
        )
        if portfolio.is_bot != is_bot:
            portfolio.is_bot = is_bot
            portfolio.save(update_fields=["is_bot"])
        return portfolio, created

    def _seed_demo_user(self):
        portfolio, created = self._portfolio_for("demo", password="demo12345")
        if created:
            # Give the demo account a couple of starter positions.
            for symbol, qty in [("AAPL", 50), ("NVDA", 100), ("GLD", 25)]:
                try:
                    place_order(portfolio, symbol=symbol, side="BUY",
                                order_type="MARKET", quantity=qty)
                except Exception:
                    pass
        self.stdout.write("  Demo user  : ready.")

    def _seed_bots(self):
        symbols = list(Instrument.objects.values_list("symbol", flat=True))
        for name in BOTS:
            portfolio, created = self._portfolio_for(name, is_bot=True)
            if created and symbols:
                for _ in range(random.randint(2, 5)):
                    try:
                        place_order(
                            portfolio,
                            symbol=random.choice(symbols),
                            side="BUY",
                            order_type="MARKET",
                            quantity=random.randint(10, 80),
                        )
                    except Exception:
                        pass
        self.stdout.write(f"  Bot traders: {len(BOTS)} ready.")

    def _seed_superuser(self):
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@example.com", "admin12345")
