"""Auto-provision a funded portfolio whenever a new user is created."""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Portfolio

User = get_user_model()


@receiver(post_save, sender=User)
def create_portfolio_for_new_user(sender, instance, created, **kwargs):
    if not created:
        return
    from decimal import Decimal

    starting = Decimal(str(settings.MARKET_ENGINE.get("STARTING_CASH", 100_000)))
    Portfolio.objects.get_or_create(
        user=instance, defaults={"cash_balance": starting}
    )
