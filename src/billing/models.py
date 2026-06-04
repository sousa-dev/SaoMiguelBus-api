"""Billing models.

``Subscription`` is the legacy email allow-list (compat with the old
subscriptions app). ``Entitlement`` is the unified, source-aware source of
truth for premium across legacy, manual grants, and (future) RevenueCat/Stripe.
"""

from django.conf import settings
from django.core.validators import EmailValidator
from django.db import models


def default_features() -> list:
    return ['ad_removal']


class Subscription(models.Model):
    id = models.AutoField(primary_key=True)
    email = models.EmailField(validators=[EmailValidator()], unique=True)
    is_active = models.BooleanField(default=True)
    verification_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subscriptions'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self) -> str:
        status = 'Active' if self.is_active else 'Inactive'
        return f'{self.email} - {status}'


class Entitlement(models.Model):
    """Unified premium entitlement — one row per (user/email, source)."""

    TIER_FREE = 'free'
    TIER_PREMIUM = 'premium'
    TIER_CHOICES = [(TIER_FREE, 'Free'), (TIER_PREMIUM, 'Premium')]

    SOURCE_LEGACY = 'legacy_email'
    SOURCE_MANUAL = 'manual'
    SOURCE_REVENUECAT = 'revenuecat'
    SOURCE_STRIPE = 'stripe'
    SOURCE_CHOICES = [
        (SOURCE_LEGACY, 'Legacy email allow-list'),
        (SOURCE_MANUAL, 'Manual grant'),
        (SOURCE_REVENUECAT, 'RevenueCat (IAP)'),
        (SOURCE_STRIPE, 'Stripe'),
    ]

    STATUS_ACTIVE = 'active'
    STATUS_CANCELED = 'canceled'
    STATUS_EXPIRED = 'expired'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_CANCELED, 'Canceled'),
        (STATUS_EXPIRED, 'Expired'),
    ]

    PLATFORM_CHOICES = [('ios', 'iOS'), ('android', 'Android'), ('web', 'Web')]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='entitlements',
        null=True,
        blank=True,
    )
    email = models.EmailField(blank=True, db_index=True)
    tier = models.CharField(max_length=16, choices=TIER_CHOICES, default=TIER_PREMIUM)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES, blank=True)
    external_id = models.CharField(max_length=255, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    features = models.JSONField(default=default_features)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'billing_entitlement'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'source'],
                name='uniq_entitlement_user_source',
                condition=models.Q(user__isnull=False),
            ),
        ]
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['email', 'status']),
            models.Index(fields=['source', 'status']),
        ]

    def __str__(self) -> str:
        who = self.user_id or self.email or 'unlinked'
        return f'{who} - {self.tier}/{self.source} ({self.status})'

    @property
    def is_active(self) -> bool:
        return self.status == self.STATUS_ACTIVE and self.tier == self.TIER_PREMIUM
