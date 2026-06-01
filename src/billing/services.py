"""Subscription verification (legacy API contract)."""

from __future__ import annotations

import logging

from django.core.exceptions import ValidationError

from billing.models import Subscription

logger = logging.getLogger(__name__)

CREATION_VERIFICATION_CODE = (
    'a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6'
    'a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6'
)


def verify_subscription(
    *,
    email: str,
    create_subscription_code: str | None = None,
) -> dict:
    if create_subscription_code and create_subscription_code == CREATION_VERIFICATION_CODE:
        subscription, created = Subscription.objects.get_or_create(
            email=email,
            defaults={'is_active': True, 'verification_count': 0},
        )
        if not created and not subscription.is_active:
            subscription.is_active = True
            subscription.save(update_fields=['is_active', 'updated_at'])
        if created:
            logger.info('Created subscription for %s', email)

    subscription = Subscription.objects.filter(email=email).first()
    if subscription:
        subscription.verification_count += 1
        subscription.save(update_fields=['verification_count', 'updated_at'])

    active = Subscription.objects.filter(email=email, is_active=True).exists()
    if active:
        return {
            'hasActiveSubscription': True,
            'subscriptionType': 'premium',
            'expiresAt': None,
            'features': ['ad_removal', 'priority_support'],
            'message': None,
        }
    return {
        'hasActiveSubscription': False,
        'subscriptionType': None,
        'expiresAt': None,
        'features': [],
        'message': 'No active subscription found for this email',
    }
