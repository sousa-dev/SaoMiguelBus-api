"""Eleven Systems PDL Mini Bus live AVL HTTP client.

Requests are routed through `shared.upstream_proxy`, which sends the target host
in a header and preserves the full upstream path. That lets one Pi serve both
this and AzoresBus without a per-service path mapping — see
minibus/docs/tailscale-tracking-proxy.md.

MINIBUS_TRACKING_BASE_URL remains the upstream ORIGIN plus base path. Setting
UPSTREAM_PROXY_URL is what moves traffic through the Pi; with it unset, calls go
direct, so local development and tests need no proxy.
"""

from __future__ import annotations

import logging
from typing import Any

import requests
from decouple import config

from shared.upstream_proxy import build_request

logger = logging.getLogger(__name__)

MINIBUS_TRACKING_BASE_URL = config(
    'MINIBUS_TRACKING_BASE_URL',
    default='https://pdl.elevensystems.pt/publicapi',
).rstrip('/')
MINIBUS_TRACKING_PROXY_KEY = config('MINIBUS_TRACKING_PROXY_KEY', default='')
MINIBUS_TRACKING_TIMEOUT = config('MINIBUS_TRACKING_TIMEOUT', default=10, cast=int)

_TRACKING_PROXY_KEY_HEADER = 'X-Tracking-Proxy-Key'


class MinibusTrackingError(Exception):
    """Eleven Systems AVL API failure."""


class MinibusTrackingNotFoundError(MinibusTrackingError):
    """Vehicle tracking id not found upstream."""


def fetch_fleet_locations() -> list[dict[str, Any]]:
    """Fetch all active vehicle locations."""
    url, headers = _resolve('/locations')
    payload = _request_json(url, not_found_exc=MinibusTrackingError, headers=headers)
    if not isinstance(payload, list):
        raise MinibusTrackingError('Unexpected fleet response shape')
    return payload


def fetch_vehicle_location(tracking_id: str) -> dict[str, Any]:
    """Fetch live detail for one vehicle."""
    tracking_id = str(tracking_id).strip()
    if not tracking_id:
        raise MinibusTrackingNotFoundError('Vehicle id required')
    url, headers = _resolve(f'/locations/{tracking_id}')
    payload = _request_json(
        url, not_found_exc=MinibusTrackingNotFoundError, headers=headers,
    )
    if not isinstance(payload, dict):
        raise MinibusTrackingError('Unexpected vehicle detail response shape')
    return payload


def _tracking_headers() -> dict[str, str]:
    """Legacy direct-proxy key, kept for a proxy not yet on the new contract."""
    if not MINIBUS_TRACKING_PROXY_KEY:
        return {}
    return {_TRACKING_PROXY_KEY_HEADER: MINIBUS_TRACKING_PROXY_KEY}


def _resolve(path: str) -> tuple[str, dict[str, str]]:
    url, headers = build_request(MINIBUS_TRACKING_BASE_URL, path)
    return url, {**_tracking_headers(), **headers}


def _request_json(
    url: str,
    *,
    not_found_exc: type[MinibusTrackingError],
    headers: dict[str, str] | None = None,
) -> Any:
    try:
        response = requests.get(
            url,
            timeout=MINIBUS_TRACKING_TIMEOUT,
            headers=_tracking_headers() if headers is None else headers,
        )
    except requests.RequestException as exc:
        logger.exception('Minibus tracking request failed url=%s', url)
        raise MinibusTrackingError(str(exc)) from exc

    if response.status_code == 404:
        raise not_found_exc(f'Upstream HTTP 404 for {url}')

    if not response.ok:
        logger.warning(
            'Minibus tracking HTTP %s url=%s body=%s',
            response.status_code,
            url,
            response.text[:500],
        )
        raise MinibusTrackingError(f'Upstream HTTP {response.status_code}')

    try:
        return response.json()
    except ValueError as exc:
        raise MinibusTrackingError('Invalid JSON from upstream AVL API') from exc
