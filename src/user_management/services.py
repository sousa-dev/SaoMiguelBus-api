"""Account/auth business logic for the REST surface.

Stock ``auth.User`` is used (no custom AUTH_USER_MODEL); the lowercased email is
both the username and the account key. Legacy premium is honored on every auth
event via ``billing.services.ensure_legacy_entitlement`` (best-effort: an
entitlement hiccup never blocks authentication).
"""

from __future__ import annotations

import logging

from django.contrib.auth import authenticate, get_user_model

User = get_user_model()
logger = logging.getLogger(__name__)


def normalize_email(email: str) -> str:
    return (email or '').strip().lower()


def email_taken(email: str) -> bool:
    email = normalize_email(email)
    return (
        User.objects.filter(username__iexact=email).exists()
        or User.objects.filter(email__iexact=email).exists()
    )


def find_user_by_email(email: str):
    email = normalize_email(email)
    return (
        User.objects.filter(username__iexact=email).first()
        or User.objects.filter(email__iexact=email).first()
    )


def create_account(*, email: str, password: str | None = None, display_name: str = ''):
    email = normalize_email(email)
    user = User(username=email, email=email, first_name=(display_name or '')[:150])
    if password:
        user.set_password(password)
    else:
        user.set_unusable_password()
    user.save()
    honor_legacy_entitlement(user)
    return user


def authenticate_user(request, *, email: str, password: str):
    email = normalize_email(email)
    return authenticate(request=request, username=email, password=password)


def get_or_create_token(user):
    from rest_framework.authtoken.models import Token

    token, _ = Token.objects.get_or_create(user=user)
    return token


def rotate_token(user):
    """Invalidate any existing token (used on logout)."""
    from rest_framework.authtoken.models import Token

    Token.objects.filter(user=user).delete()


def link_social_connection(*, user, provider: str, subject: str = '', refresh_token: str = ''):
    """Create/update the user's social connection (used to revoke on deletion)."""
    from user_management.models import SocialConnection

    defaults = {'subject': subject}
    # Only overwrite a stored refresh token when we actually obtained a new one.
    if refresh_token:
        defaults['refresh_token'] = refresh_token
    connection, _ = SocialConnection.objects.update_or_create(
        user=user, provider=provider, defaults=defaults
    )
    return connection


def revoke_social_tokens(user) -> None:
    """Best-effort: revoke the user's Apple grant before the account is deleted."""
    from user_management.apple_oauth import revoke_refresh_token
    from user_management.models import SocialConnection

    try:
        connections = list(
            SocialConnection.objects.filter(
                user=user, provider=SocialConnection.PROVIDER_APPLE
            ).exclude(refresh_token='')
        )
    except Exception:  # pragma: no cover - never block deletion on a model/query hiccup
        logger.exception('Loading social connections failed for user %s', getattr(user, 'pk', None))
        return
    for connection in connections:
        revoke_refresh_token(connection.refresh_token)


def delete_account(user) -> None:
    """Permanently and irreversibly delete the account and its personal data.

    Required by App Store Guideline 5.1.1(v) / GDPR right to erasure. Revokes any
    Sign in with Apple grant first (Apple requirement for SIWA + deletion), then
    deletes the ``auth.User`` — which cascades the auth token, ``billing``
    entitlements and ``SocialConnection`` rows (FK ``on_delete=CASCADE``). The
    legacy premium allow-list row is keyed by email (no FK), so it is removed
    explicitly to avoid leaving PII behind.
    """
    revoke_social_tokens(user)
    email = normalize_email(user.email or user.username)
    if email:
        try:
            from billing.models import Subscription

            Subscription.objects.filter(email__iexact=email).delete()
        except Exception:  # pragma: no cover - never block deletion on billing errors
            logger.exception('Legacy subscription cleanup failed for user %s', getattr(user, 'pk', None))
    user.delete()


def honor_legacy_entitlement(user) -> None:
    """Best-effort: mint/refresh a legacy_email entitlement if one is owed."""
    try:
        from billing.services import ensure_legacy_entitlement

        ensure_legacy_entitlement(user)
    except Exception:  # pragma: no cover - never block auth on billing errors
        logger.exception('Legacy entitlement honoring failed for user %s', getattr(user, 'pk', None))
