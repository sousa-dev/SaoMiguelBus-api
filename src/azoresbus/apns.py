"""Apple Push Notification service client for iOS Live Activity updates.

Raw APNs over HTTP/2, deliberately NOT Expo push -- the Expo push service does
not proxy the `liveactivity` push type, so this talks to Apple directly using
the app's own APNs auth key (ES256, token-based auth: one key, no per-device
certificate to renew). `requests` cannot speak HTTP/2, which is why `httpx` is
a dependency here and nowhere else in this codebase.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx
import jwt
from decouple import config
from django.core.cache import cache

logger = logging.getLogger(__name__)

APNS_KEY_ID = config('APNS_KEY_ID', default='')
APNS_TEAM_ID = config('APNS_TEAM_ID', default='')
APNS_KEY_P8 = config('APNS_KEY_P8', default='')
APNS_BUNDLE_ID = config('APNS_BUNDLE_ID', default='com.sousadev.saomiguelhub')

PRODUCTION_HOST = 'https://api.push.apple.com'
SANDBOX_HOST = 'https://api.sandbox.push.apple.com'

# Apple rate-limits provider-token generation to roughly once per 20 minutes
# per key, and a token stays valid for about an hour. Caching well inside
# both bounds means a slow beat run, or two overlapping ones, can never mint
# a second token for nothing.
TOKEN_CACHE_TTL = 45 * 60
TOKEN_CACHE_KEY = 'azoresbus:apns:jwt'

# ActivityKit rejects a push over 4KB outright.
MAX_PAYLOAD_BYTES = 4096

EVENT_UPDATE = 'update'
EVENT_END = 'end'


class ApnsError(Exception):
    """A push attempt failed. `terminal=True` means the token itself is dead
    (unregistered or malformed) -- the caller should stop retrying it, not
    just this one push."""

    def __init__(self, message: str, *, terminal: bool = False):
        super().__init__(message)
        self.terminal = terminal


def build_provider_token(key_pem: str, key_id: str, team_id: str, *, now: int | None = None) -> str:
    """One ES256 JWT. Pure -- takes key material as arguments rather than
    reading module config, so it is testable with a throwaway EC key and
    needs no real Apple credentials."""
    issued_at = now if now is not None else int(time.time())
    return jwt.encode(
        {'iss': team_id, 'iat': issued_at},
        key_pem,
        algorithm='ES256',
        headers={'kid': key_id},
    )


def _auth_token() -> str:
    cached = cache.get(TOKEN_CACHE_KEY)
    if cached:
        return cached
    token = build_provider_token(APNS_KEY_P8, APNS_KEY_ID, APNS_TEAM_ID)
    cache.set(TOKEN_CACHE_KEY, token, TOKEN_CACHE_TTL)
    return token


def live_activity_payload(
    snapshot: dict[str, Any],
    *,
    event: str = EVENT_UPDATE,
    dismiss_in_seconds: int = 0,
) -> dict[str, Any]:
    """`{"aps": {...}}` for one push.

    Only `event="end"` carries `dismissal-date` -- that is what tells the Lock
    Screen and Dynamic Island WHEN to actually remove the card, rather than
    leaving it frozen showing its last content until Apple's own ceiling
    expires it.
    """
    aps: dict[str, Any] = {
        'timestamp': int(time.time()),
        'event': event,
        'content-state': snapshot,
    }
    if event == EVENT_END:
        aps['dismissal-date'] = int(time.time()) + max(0, dismiss_in_seconds)
    return {'aps': aps}


def push_live_activity(push_token: str, environment: str, payload: dict[str, Any]) -> None:
    """Raises `ApnsError` on any non-2xx. `terminal=True` for the two
    responses that mean the token itself is dead: 410 Unregistered, and a 400
    whose reason is BadDeviceToken."""
    body = json.dumps(payload).encode('utf-8')
    if len(body) > MAX_PAYLOAD_BYTES:
        # A caller bug (an oversized content-state), not an Apple rejection --
        # still not worth throwing bytes at Apple that will only bounce.
        raise ApnsError(f'payload too large: {len(body)} bytes')

    host = SANDBOX_HOST if environment == 'development' else PRODUCTION_HOST
    event = payload.get('aps', {}).get('event', EVENT_UPDATE)
    headers = {
        'authorization': f'bearer {_auth_token()}',
        'apns-topic': f'{APNS_BUNDLE_ID}.push-type.liveactivity',
        'apns-push-type': 'liveactivity',
        # The alight alert is time-sensitive; everything else is routine.
        'apns-priority': '10' if event == EVENT_END else '5',
        'apns-expiration': str(int(time.time()) + 3600),
    }

    try:
        with httpx.Client(http2=True, timeout=10.0) as client:
            response = client.post(f'{host}/3/device/{push_token}', content=body, headers=headers)
    except httpx.HTTPError as exc:
        raise ApnsError(f'apns request failed: {exc}') from exc

    if response.status_code == 200:
        return

    reason = ''
    try:
        reason = response.json().get('reason', '')
    except ValueError:
        pass

    terminal = response.status_code == 410 or (
        response.status_code == 400 and reason == 'BadDeviceToken'
    )
    logger.warning('apns push failed status=%s reason=%s', response.status_code, reason)
    raise ApnsError(f'apns {response.status_code}: {reason}', terminal=terminal)
