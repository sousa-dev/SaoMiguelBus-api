"""Stripe payment models.

Stores the relationship between a Django user and a Stripe Checkout Session,
tracking whether payment has been completed.
"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db import models


class UserPayment(models.Model):
    """Links a user to a Stripe Checkout Session.

    Attributes:
        app_user: FK to the Django User who initiated checkout. Nullable for
            anonymous purchases.
        email: Customer email captured from Stripe after payment.
        payment_bool: ``True`` once payment is confirmed.
        stripe_checkout_id: The Stripe Checkout Session ID.
    """

    app_user = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL
    )
    email = models.EmailField(null=True, blank=True)
    payment_bool = models.BooleanField(default=False)
    stripe_checkout_id = models.CharField(max_length=500)

    class Meta:
        indexes = [
            models.Index(fields=["stripe_checkout_id"]),
        ]

    def __str__(self) -> str:
        status = "paid" if self.payment_bool else "pending"
        return f"Payment({self.stripe_checkout_id[:12]}… — {status})"
