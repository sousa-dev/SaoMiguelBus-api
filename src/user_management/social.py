"""Server-side verification of native Apple / Google identity tokens.

The mobile client obtains the provider identity token natively
(``expo-apple-authentication`` / native Google sign-in) and POSTs it to
``/api/v3/auth/social``. We verify the JWT signature, audience, issuer and
expiry against the provider's public JWKS, then trust only the verified email.
No browser-redirect OAuth flow is involved.
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt
from django.conf import settings
from jwt import PyJWKClient

APPLE_ISSUER = 'https://appleid.apple.com'
APPLE_JWKS_URL = 'https://appleid.apple.com/auth/keys'
GOOGLE_ISSUERS = {'https://accounts.google.com', 'accounts.google.com'}
GOOGLE_JWKS_URL = 'https://www.googleapis.com/oauth2/v3/certs'


class SocialVerificationError(Exception):
    """Raised when a provider identity token fails verification."""


@dataclass
class SocialIdentity:
    email: str
    name: str = ''
    provider: str = ''
    subject: str = ''


_jwk_clients: dict[str, PyJWKClient] = {}


def social_auth_capabilities() -> dict[str, bool]:
    """Provider availability for v3 bootstrap (mobile sign-in button gating)."""
    return {
        'google': bool(getattr(settings, 'GOOGLE_OAUTH_CLIENT_IDS', [])),
        'apple': bool(getattr(settings, 'APPLE_BUNDLE_IDS', [])),
    }


def _jwk_client(url: str) -> PyJWKClient:
    client = _jwk_clients.get(url)
    if client is None:
        client = PyJWKClient(url, cache_keys=True)
        _jwk_clients[url] = client
    return client


def _decode(identity_token: str, *, jwks_url: str, audiences: list[str]) -> dict:
    if not audiences:
        raise SocialVerificationError('No configured client ids / bundle ids for this provider')
    try:
        signing_key = _jwk_client(jwks_url).get_signing_key_from_jwt(identity_token)
        return jwt.decode(
            identity_token,
            signing_key.key,
            algorithms=['RS256'],
            audience=audiences,
            options={'require': ['exp', 'iss', 'aud']},
        )
    except SocialVerificationError:
        raise
    except Exception as exc:  # noqa: BLE001 - normalize all jwt/network errors
        raise SocialVerificationError(f'Identity token verification failed: {exc}') from exc


def verify_social_identity(*, provider: str, identity_token: str, nonce: str | None = None) -> SocialIdentity:
    if provider == 'apple':
        claims = _decode(
            identity_token,
            jwks_url=APPLE_JWKS_URL,
            audiences=list(getattr(settings, 'APPLE_BUNDLE_IDS', [])),
        )
        if claims.get('iss') != APPLE_ISSUER:
            raise SocialVerificationError('Unexpected token issuer')
    elif provider == 'google':
        claims = _decode(
            identity_token,
            jwks_url=GOOGLE_JWKS_URL,
            audiences=list(getattr(settings, 'GOOGLE_OAUTH_CLIENT_IDS', [])),
        )
        if claims.get('iss') not in GOOGLE_ISSUERS:
            raise SocialVerificationError('Unexpected token issuer')
        if str(claims.get('email_verified', 'true')).lower() == 'false':
            raise SocialVerificationError('Provider email is not verified')
    else:
        raise SocialVerificationError(f'Unsupported provider: {provider}')

    email = (claims.get('email') or '').strip().lower()
    if not email:
        raise SocialVerificationError('No email present in identity token')

    if nonce and claims.get('nonce') and claims['nonce'] != nonce:
        raise SocialVerificationError('Nonce mismatch')

    return SocialIdentity(
        email=email,
        name=claims.get('name') or '',
        provider=provider,
        subject=claims.get('sub') or '',
    )
