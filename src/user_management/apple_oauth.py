"""Sign in with Apple server-to-server helpers.

Used to (a) exchange the native ``authorizationCode`` for a refresh token at
sign-in and (b) revoke that token when the account is deleted, as required for
apps that offer Sign in with Apple + account deletion.

All functions are best-effort and config-gated: when the AuthKey is not
configured (``APPLE_PRIVATE_KEY``/``APPLE_KEY_ID`` empty) they no-op so sign-in
and account deletion keep working in environments without Apple credentials.
"""

from __future__ import annotations

import logging
import time

import jwt
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

APPLE_TOKEN_URL = 'https://appleid.apple.com/auth/token'
APPLE_REVOKE_URL = 'https://appleid.apple.com/auth/revoke'
_AUDIENCE = 'https://appleid.apple.com'
_TIMEOUT = 10


def is_configured() -> bool:
    return bool(
        getattr(settings, 'APPLE_PRIVATE_KEY', '')
        and getattr(settings, 'APPLE_KEY_ID', '')
        and getattr(settings, 'APPLE_TEAM_ID', '')
        and getattr(settings, 'APPLE_CLIENT_ID', '')
    )


def _client_secret() -> str:
    now = int(time.time())
    return jwt.encode(
        {
            'iss': settings.APPLE_TEAM_ID,
            'iat': now,
            'exp': now + 1800,
            'aud': _AUDIENCE,
            'sub': settings.APPLE_CLIENT_ID,
        },
        settings.APPLE_PRIVATE_KEY,
        algorithm='ES256',
        headers={'kid': settings.APPLE_KEY_ID},
    )


def exchange_code_for_refresh_token(authorization_code: str) -> str | None:
    """Exchange a native authorization code for a long-lived refresh token."""
    if not authorization_code or not is_configured():
        return None
    try:
        resp = requests.post(
            APPLE_TOKEN_URL,
            data={
                'client_id': settings.APPLE_CLIENT_ID,
                'client_secret': _client_secret(),
                'code': authorization_code,
                'grant_type': 'authorization_code',
            },
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning('Apple token exchange failed (%s): %s', resp.status_code, resp.text[:200])
            return None
        return resp.json().get('refresh_token') or None
    except Exception:  # pragma: no cover - network/credential errors never block sign-in
        logger.exception('Apple token exchange errored')
        return None


def revoke_refresh_token(refresh_token: str) -> bool:
    """Revoke a previously issued Apple refresh token. Returns True on success."""
    if not refresh_token or not is_configured():
        return False
    try:
        resp = requests.post(
            APPLE_REVOKE_URL,
            data={
                'client_id': settings.APPLE_CLIENT_ID,
                'client_secret': _client_secret(),
                'token': refresh_token,
                'token_type_hint': 'refresh_token',
            },
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=_TIMEOUT,
        )
        # Apple returns 200 with an empty body on success.
        if resp.status_code == 200:
            return True
        logger.warning('Apple token revoke failed (%s): %s', resp.status_code, resp.text[:200])
        return False
    except Exception:  # pragma: no cover - never block account deletion on revoke errors
        logger.exception('Apple token revoke errored')
        return False
