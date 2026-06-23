"""Eleven Systems PDL Mini Bus live AVL HTTP client."""

from __future__ import annotations

import logging
from typing import Any

import requests
from decouple import config

logger = logging.getLogger(__name__)

MINIBUS_TRACKING_BASE_URL = config(
    'MINIBUS_TRACKING_BASE_URL',
    default='https://pdl.elevensystems.pt/publicapi',
).rstrip('/')
MINIBUS_TRACKING_TIMEOUT = config('MINIBUS_TRACKING_TIMEOUT', default=10, cast=int)


class MinibusTrackingError(Exception):
    """Eleven Systems AVL API failure."""


class MinibusTrackingNotFoundError(MinibusTrackingError):
    """Vehicle tracking id not found upstream."""


def fetch_fleet_locations() -> list[dict[str, Any]]:
    """Fetch all active vehicle locations."""
    url = f'{MINIBUS_TRACKING_BASE_URL}/locations'
    payload = _request_json(url, not_found_exc=MinibusTrackingError)
    if not isinstance(payload, list):
        raise MinibusTrackingError('Unexpected fleet response shape')
    return payload


def fetch_vehicle_location(tracking_id: str) -> dict[str, Any]:
    """Fetch live detail for one vehicle."""
    tracking_id = str(tracking_id).strip()
    if not tracking_id:
        raise MinibusTrackingNotFoundError('Vehicle id required')
    url = f'{MINIBUS_TRACKING_BASE_URL}/locations/{tracking_id}'
    payload = _request_json(url, not_found_exc=MinibusTrackingNotFoundError)
    if not isinstance(payload, dict):
        raise MinibusTrackingError('Unexpected vehicle detail response shape')
    return payload


def _request_json(url: str, *, not_found_exc: type[MinibusTrackingError]) -> Any:
    try:
        response = requests.get(url, timeout=MINIBUS_TRACKING_TIMEOUT)
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
