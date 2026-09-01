"""AzoresBus live vehicle locations.

Same vendor as PDL Mini Bus, so the payload shapes are already known — but the
LIST and DETAIL responses are DIFFERENT key sets and must not share a serializer
(98 claim 14):

    list    color, id, position, status
    detail  currentStopSequence, fleetId, id, journey, licensePlate,
            position, route, speed, status      <- no top-level `color`

Colour lives on `detail.route.color`, so a map marker built from the list and a
sheet built from the detail read it from different places.

The fleet reports live as of September 2026 (29-41 vehicles during service
hours). Empty is still the correct answer at 03:00 — it is not an error.

Two shape traps, both load-bearing:

  * LIST `status` is PUNCTUALITY (`ontime`/`delayed`) and `busStatus` is the
    MOVEMENT state (`incomingAt`/`idleAt`/`inTransitTo`). DETAIL `status` carries
    the movement state instead. Serialising only `status` from the list makes
    every vehicle read "on time" forever, which is why `busStatus` is carried.
  * LIST carries no route at all, so line identity is attached downstream by
    `services_route_index`; `color` cannot stand in for it, because 49 of the 56
    routes share `2D59A9` — the colour is a service class, not a line.
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


def fetch_routes() -> list[dict[str, Any]]:
    """The route catalogue: 56 routes, ~6KB, effectively static."""
    payload = _request('/routes', not_found=AzoresbusTrackingError)
    if not isinstance(payload, list):
        raise AzoresbusTrackingError('Unexpected routes response shape')
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


def serialize_route(raw: dict) -> dict:
    """One entry of the route catalogue, and the `route` block on a vehicle."""
    return {
        'id': str(raw.get('id', '')),
        'nameShort': raw.get('nameShort', ''),
        'name': raw.get('name', ''),
        'color': raw.get('color', ''),
    }


def serialize_circulation(raw: dict) -> dict:
    """One scheduled stop on a vehicle's journey.

    `dueInMinutes` is present only from `currentStopSequence` onwards — upstream
    omits it for stops already passed, so `None` means "behind us", not "unknown".
    """
    stage = raw.get('stage') or {}
    position = stage.get('position') or {}
    return {
        'sequence': raw.get('sequence'),
        'stage': {
            'id': str(stage.get('id', '')),
            'name': stage.get('name', ''),
            'nameShort': stage.get('nameShort', ''),
            'position': {'lat': position.get('lat'), 'lon': position.get('lon')},
        },
        'departureTime': raw.get('departureTime'),
        'arrivalTime': raw.get('arrivalTime'),
        'dueInMinutes': raw.get('dueInMinutes'),
    }


def serialize_fleet_vehicle(raw: dict) -> dict:
    """LIST shape.

    `route` is a slot, filled in by `services_route_index.enrich_fleet` — it is
    emitted as None rather than omitted so the key set is stable whether or not
    the route index is warm, and clients never branch on key presence.
    """
    return {
        'id': str(raw.get('id', '')),
        'position': raw.get('position') or {},
        # Punctuality here; movement state is busStatus. See module docstring.
        'status': raw.get('status', ''),
        'busStatus': raw.get('busStatus', ''),
        'delay': raw.get('delay'),
        'speed': raw.get('speed'),
        'color': raw.get('color', ''),
        'route': None,
    }


def serialize_vehicle_detail(raw: dict) -> dict:
    """DETAIL shape. Note there is NO top-level color -- it is on `route`.

    `journey.circulations` is the whole point of the detail call: it is the stop
    list with live ETAs, and dropping it (as this serializer used to) leaves the
    app with a vehicle it can place on a map but say nothing useful about.
    Sorted here so the client does not re-sort a 105-entry list every render.
    """
    route = raw.get('route') or {}
    journey = raw.get('journey') or {}
    circulations = [
        serialize_circulation(circulation)
        for circulation in journey.get('circulations') or []
    ]
    circulations.sort(key=lambda item: item['sequence'] if item['sequence'] is not None else 0)
    return {
        'id': str(raw.get('id', '')),
        'fleetId': raw.get('fleetId', ''),
        'licensePlate': raw.get('licensePlate', ''),
        'position': raw.get('position') or {},
        'speed': raw.get('speed'),
        # Movement state here; the LIST puts punctuality in this same key.
        'status': raw.get('status', ''),
        'currentStopSequence': raw.get('currentStopSequence'),
        'route': serialize_route(route),
        'journey': {
            'id': str(journey.get('id', '')),
            'type': journey.get('type', ''),
            'shape': journey.get('shape', ''),
            'name': journey.get('name', ''),
            'start': journey.get('start', ''),
            'end': journey.get('end', ''),
            'startTime': journey.get('startTime'),
            'endTime': journey.get('endTime'),
            'direction': journey.get('direction'),
            'isActive': journey.get('isActive'),
            'circulations': circulations,
        },
    }
