"""Billing services: legacy subscription verify + unified entitlement resolution."""

from __future__ import annotations

import datetime as _dt
import logging

from django.contrib.auth import get_user_model
from django.utils import timezone

from billing.models import Entitlement, Subscription

logger = logging.getLogger(__name__)
User = get_user_model()

CREATION_VERIFICATION_CODE = (
    'a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6'
    'a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6'
)

# Higher wins when a user holds multiple active entitlements.
_SOURCE_PRIORITY = {
    Entitlement.SOURCE_STRIPE: 3,
    Entitlement.SOURCE_REVENUECAT: 3,
    Entitlement.SOURCE_MANUAL: 2,
    Entitlement.SOURCE_LEGACY: 1,
}


def normalize_email(email: str) -> str:
    return (email or '').strip().lower()


def verify_subscription(
    *,
    email: str,
    create_subscription_code: str | None = None,
) -> dict:
    email = normalize_email(email)
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

    subscription = Subscription.objects.filter(email__iexact=email).first()
    if subscription:
        subscription.verification_count += 1
        subscription.save(update_fields=['verification_count', 'updated_at'])

    active = Subscription.objects.filter(email__iexact=email, is_active=True).exists()
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


def ensure_legacy_entitlement(user) -> Entitlement | None:
    """Honor an active legacy email subscription as a revocable entitlement.

    Idempotent: safe to call on every register/login/social event.
    """
    email = normalize_email(getattr(user, 'email', ''))
    if not email:
        return None

    legacy_active = Subscription.objects.filter(email__iexact=email, is_active=True).exists()
    entitlement = Entitlement.objects.filter(user=user, source=Entitlement.SOURCE_LEGACY).first()

    if legacy_active:
        if entitlement is None:
            entitlement = Entitlement.objects.create(
                user=user,
                email=email,
                source=Entitlement.SOURCE_LEGACY,
                tier=Entitlement.TIER_PREMIUM,
                status=Entitlement.STATUS_ACTIVE,
            )
        elif entitlement.status != Entitlement.STATUS_ACTIVE or entitlement.tier != Entitlement.TIER_PREMIUM:
            entitlement.status = Entitlement.STATUS_ACTIVE
            entitlement.tier = Entitlement.TIER_PREMIUM
            entitlement.save(update_fields=['status', 'tier', 'updated_at'])
        return entitlement

    # Legacy access withdrawn: expire a previously-honored entitlement.
    if entitlement and entitlement.status == Entitlement.STATUS_ACTIVE:
        entitlement.status = Entitlement.STATUS_EXPIRED
        entitlement.save(update_fields=['status', 'updated_at'])
    return None


def resolve_entitlement(user) -> Entitlement | None:
    """Return the highest-priority active premium entitlement for ``user``."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return None
    now = timezone.now()
    candidates = [
        e
        for e in Entitlement.objects.filter(
            user=user,
            status=Entitlement.STATUS_ACTIVE,
            tier=Entitlement.TIER_PREMIUM,
        )
        if e.current_period_end is None or e.current_period_end > now
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda e: _SOURCE_PRIORITY.get(e.source, 0))


def manage_via(entitlement: Entitlement | None) -> str:
    """Where the user manages/cancels this subscription."""
    if entitlement is None:
        return 'none'
    if entitlement.source == Entitlement.SOURCE_STRIPE:
        return 'stripe'
    if entitlement.source == Entitlement.SOURCE_REVENUECAT:
        return 'play_store' if entitlement.platform == 'android' else 'app_store'
    return 'none'  # legacy_email / manual are managed by us, not a store


def entitlement_response(user) -> dict:
    """The /api/v3/billing/entitlement payload (always well-formed, never errors)."""
    entitlement = resolve_entitlement(user)
    if entitlement is None:
        return {
            'tier': Entitlement.TIER_FREE,
            'source': None,
            'status': None,
            'currentPeriodEnd': None,
            'features': [],
            'manageVia': 'none',
        }
    return {
        'tier': entitlement.tier,
        'source': entitlement.source,
        'status': entitlement.status,
        'currentPeriodEnd': (
            entitlement.current_period_end.isoformat() if entitlement.current_period_end else None
        ),
        'features': entitlement.features or [],
        'manageVia': manage_via(entitlement),
    }


def _datetime_from_ms(ms) -> _dt.datetime | None:
    if not ms:
        return None
    try:
        return _dt.datetime.fromtimestamp(int(ms) / 1000, tz=_dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def reconcile_revenuecat(event: dict) -> Entitlement | None:
    """Reconcile a RevenueCat webhook event into an Entitlement (future-IAP seam).

    Expects the client to set RevenueCat ``app_user_id`` to the Django user id
    (or username/email). Unknown users are ignored.
    """
    app_user_id = event.get('app_user_id') or event.get('original_app_user_id')
    if not app_user_id:
        return None

    user = None
    if str(app_user_id).isdigit():
        user = User.objects.filter(pk=int(app_user_id)).first()
    if user is None:
        user = (
            User.objects.filter(username__iexact=str(app_user_id)).first()
            or User.objects.filter(email__iexact=str(app_user_id)).first()
        )
    if user is None:
        logger.warning('RevenueCat event for unknown app_user_id=%s', app_user_id)
        return None

    store = (event.get('store') or '').upper()
    platform = 'android' if store == 'PLAY_STORE' else 'ios' if store == 'APP_STORE' else ''

    event_type = (event.get('type') or '').upper()
    if event_type in {'CANCELLATION'}:
        status_value = Entitlement.STATUS_CANCELED
    elif event_type in {'EXPIRATION', 'SUBSCRIPTION_PAUSED', 'BILLING_ISSUE'}:
        status_value = Entitlement.STATUS_EXPIRED
    else:
        status_value = Entitlement.STATUS_ACTIVE

    entitlement, _ = Entitlement.objects.update_or_create(
        user=user,
        source=Entitlement.SOURCE_REVENUECAT,
        defaults={
            'email': normalize_email(user.email),
            'tier': Entitlement.TIER_PREMIUM,
            'status': status_value,
            'platform': platform,
            'external_id': str(app_user_id),
            'current_period_end': _datetime_from_ms(event.get('expiration_at_ms')),
        },
    )
    return entitlement
