"""AzoresBus live vehicle locations.

Same vendor as PDL Mini Bus, so the payload shapes are already known — but the
LIST and DETAIL responses are DIFFERENT key sets and must not share a serializer
(98 claim 14):

    list    color, id, position, status
    detail  currentStopSequence, fleetId, id, journey, licensePlate,
            position, route, speed, status      <- no top-level `color`

Colour lives on `detail.route.color`, so a map marker built from the list and a
sheet built from the detail read it from different places.

The endpoint answers today and returns `[]`: AzoresBus vehicles are not
reporting yet. Empty is the correct answer at 03:00 and the correct answer now —
it is not an error.
"""

from __future__ import annotations

import logging
from typing import Any

import requests
from decouple import config

from shared.upstream_proxy import build_request

logger = logging.getLogger(__name__)

AZORESBUS_TRACKING_BASE_URL = config(
    'AZORESBUS_TRACKING_BASE_URL',
    default='https://azb.elevensystems.pt/api',
).rstrip('/')
AZORESBUS_TRACKING_TIMEOUT = config(
    'AZORESBUS_TRACKING_TIMEOUT', default=10, cast=int,
)

USER_AGENT = (
    'SaoMiguelBus/3.x tracking (+https://saomiguelbus.com; '
    'contact@saomiguelbus.com)'
)


class AzoresbusTrackingError(Exception):
    """Upstream AVL failure."""


class AzoresbusVehicleNotFound(AzoresbusTrackingError):
    """Vehicle id not known upstream."""


def fetch_fleet_locations() -> list[dict[str, Any]]:
    payload = _request('/locations', not_found=AzoresbusTrackingError)
    if not isinstance(payload, list):
        raise AzoresbusTrackingError('Unexpected fleet response shape')
    return payload


def fetch_vehicle_location(vehicle_id: str) -> dict[str, Any]:
    vehicle_id = str(vehicle_id).strip()
    if not vehicle_id:
        raise AzoresbusVehicleNotFound('Vehicle id required')
    payload = _request(
        f'/locations/{vehicle_id}', not_found=AzoresbusVehicleNotFound,
    )
    if not isinstance(payload, dict):
        raise AzoresbusTrackingError('Unexpected vehicle detail shape')
    return payload


def _request(path: str, *, not_found: type[AzoresbusTrackingError]) -> Any:
    url, proxy_headers = build_request(AZORESBUS_TRACKING_BASE_URL, path)
    headers = {'User-Agent': USER_AGENT, 'Accept': 'application/json'}
    headers.update(proxy_headers)

    try:
        response = requests.get(
            url, timeout=AZORESBUS_TRACKING_TIMEOUT, headers=headers,
        )
    except requests.RequestException as exc:
        logger.exception('azoresbus tracking request failed url=%s', url)
        raise AzoresbusTrackingError(str(exc)) from exc

    if response.status_code == 404:
        raise not_found(f'Upstream HTTP 404 for {path}')

    if not response.ok:
        logger.warning('azoresbus tracking HTTP %s url=%s body=%s',
                       response.status_code, url, response.text[:500])
        raise AzoresbusTrackingError(f'Upstream HTTP {response.status_code}')

    try:
        return response.json()
    except ValueError as exc:
        raise AzoresbusTrackingError('Invalid JSON from upstream AVL') from exc


def serialize_fleet_vehicle(raw: dict) -> dict:
    """LIST shape: exactly color, id, position, status."""
    return {
        'id': str(raw.get('id', '')),
        'position': raw.get('position') or {},
        'status': raw.get('status', ''),
        'color': raw.get('color', ''),
    }


def serialize_vehicle_detail(raw: dict) -> dict:
    """DETAIL shape. Note there is NO top-level color -- it is on `route`."""
    route = raw.get('route') or {}
    journey = raw.get('journey') or {}
    return {
        'id': str(raw.get('id', '')),
        'fleetId': raw.get('fleetId', ''),
        'licensePlate': raw.get('licensePlate', ''),
        'position': raw.get('position') or {},
        'speed': raw.get('speed'),
        'status': raw.get('status', ''),
        'currentStopSequence': raw.get('currentStopSequence'),
        'route': {
            'id': str(route.get('id', '')),
            'nameShort': route.get('nameShort', ''),
            'name': route.get('name', ''),
            'color': route.get('color', ''),
        },
        'journey': {
            'id': str(journey.get('id', '')),
            'type': journey.get('type', ''),
            'shape': journey.get('shape', ''),
        },
    }
