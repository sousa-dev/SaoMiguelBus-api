"""Cached, flag-gated access to the AzoresBus fleet.

Three distinct states, and conflating them is the easy mistake (02 §8):

    tracking_disabled   the feature flag is off        -> 503
    empty fleet         nobody is reporting            -> 200 []
    upstream failure    the AVL API is down            -> 502

Caching, locking and stale-grace come from `shared.tracking_cache`, which minibus
grew first; see that module for the envelope semantics. Everything here is keyed
per island, because a second island's fleet must not be served from the first
one's cache.
"""

from __future__ import annotations

import logging

from decouple import config
from django.core.cache import cache

from azoresbus.tracking_client import (
    AzoresbusTrackingError,
    fetch_fleet_locations,
    fetch_vehicle_location,
    serialize_fleet_vehicle,
    serialize_vehicle_detail,
)
from azoresbus.services_stop_identity import safe_stop_identity_map
from shared.tracking_cache import CacheMeta, cached_fetch, clamp
from transit.services.schedule_phase import azoresbus_flags

logger = logging.getLogger(__name__)

CACHE_TTL_MIN = 1
CACHE_TTL_MAX = 300
STALE_GRACE_MAX = 600
LOCK_TTL_MAX = 30
HEALTH_CACHE_TTL_MIN = 5
HEALTH_CACHE_TTL_MAX = 120


class TrackingDisabled(Exception):
    """The feature flag is off. Not an error, a configuration."""


def tracking_enabled(island) -> bool:
    return bool(azoresbus_flags(island).get('trackingEnabled', False))


def get_tracking_config() -> dict[str, int]:
    return {
        'cache_ttl': clamp(
            # Kept in step with AZORESBUS_TRACKING_POLL_MS on the client.
            config('AZORESBUS_TRACKING_CACHE_TTL', default=60, cast=int),
            CACHE_TTL_MIN, CACHE_TTL_MAX,
        ),
        'stale_grace': clamp(
            # MUST exceed the cache TTL, or the stale window (ttl < age <=
            # grace) is empty and a brief blip blanks the map instead of
            # serving the last good fleet. Three TTLs of cover.
            config('AZORESBUS_TRACKING_STALE_GRACE', default=180, cast=int),
            0, STALE_GRACE_MAX,
        ),
        'lock_ttl': clamp(
            config('AZORESBUS_TRACKING_LOCK_TTL', default=5, cast=int),
            1, LOCK_TTL_MAX,
        ),
    }


def get_health_cache_config() -> dict[str, int]:
    return {
        'health_cache_ttl': clamp(
            config('AZORESBUS_TRACKING_HEALTH_CACHE_TTL', default=30, cast=int),
            HEALTH_CACHE_TTL_MIN, HEALTH_CACHE_TTL_MAX,
        ),
    }


def fleet_cache_key(island_key: str) -> str:
    return f'azoresbus:tracking:fleet:{island_key}'


def _fleet_lock_key(island_key: str) -> str:
    return f'azoresbus:tracking:lock:fleet:{island_key}'


def vehicle_cache_key(island_key: str, vehicle_id: str) -> str:
    return f'azoresbus:tracking:vehicle:{island_key}:{vehicle_id}'


def _vehicle_lock_key(island_key: str, vehicle_id: str) -> str:
    return f'azoresbus:tracking:lock:vehicle:{island_key}:{vehicle_id}'


def _health_cache_key(island_key: str) -> str:
    return f'azoresbus:tracking:health:{island_key}'


def get_fleet(island) -> list[dict]:
    if not tracking_enabled(island):
        raise TrackingDisabled('tracking_disabled')

    cfg = get_tracking_config()
    raw, _meta = cached_fetch(
        cache_key=fleet_cache_key(island.key),
        lock_key=_fleet_lock_key(island.key),
        fetch_fn=fetch_fleet_locations,
        cache_ttl=cfg['cache_ttl'],
        stale_grace=cfg['stale_grace'],
        lock_ttl=cfg['lock_ttl'],
        error_type=AzoresbusTrackingError,
    )
    vehicles = [serialize_fleet_vehicle(item) for item in raw]

    # Imported here rather than at module scope: the route index imports this
    # module's config helpers, and enrichment is strictly a decoration of a fleet
    # that is already correct without it.
    from azoresbus.services_route_index import enrich_fleet

    try:
        return enrich_fleet(island, vehicles)
    except Exception:  # noqa: BLE001 - never fail a good fleet over a nicety
        logger.exception('azoresbus route enrichment failed; serving unenriched')
        return vehicles


def get_vehicle(island, vehicle_id: str) -> dict:
    if not tracking_enabled(island):
        raise TrackingDisabled('tracking_disabled')

    cfg = get_tracking_config()
    raw, _meta = cached_fetch(
        cache_key=vehicle_cache_key(island.key, vehicle_id),
        lock_key=_vehicle_lock_key(island.key, vehicle_id),
        fetch_fn=lambda: fetch_vehicle_location(vehicle_id),
        cache_ttl=cfg['cache_ttl'],
        stale_grace=cfg['stale_grace'],
        lock_ttl=cfg['lock_ttl'],
        error_type=AzoresbusTrackingError,
    )
    # Read here, on the request thread, rather than inside the serializer: the
    # tracking client is imported by the route-index sweep's worker threads and
    # must stay free of the ORM.
    return serialize_vehicle_detail(raw, safe_stop_identity_map(island))


def get_tracking_health(island, *, force: bool = False) -> dict:
    """Availability probe, cached separately from the fleet.

    `force` exists for the client's "Try again" button: without a bypass it would
    keep being handed the cached verdict and look broken.

    It bypasses this verdict cache only -- the fleet keeps its own short TTL
    underneath. That is deliberate: Try Again is only on screen while tracking is
    unavailable, and in that state there is no fresh fleet to serve, so the
    forced call does reach upstream. Making it punch through the fleet cache too
    would hand every user a button that stampedes the Pi.
    """
    if not tracking_enabled(island):
        return {'status': 'disabled', 'vehicles': 0}

    cache_key = _health_cache_key(island.key)
    if not force:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    try:
        fleet = get_fleet(island)
    except AzoresbusTrackingError:
        # Deliberately not cached: an outage should recover on the next poll
        # rather than being pinned for the health TTL.
        raise

    result = {'status': 'ok', 'vehicles': len(fleet)}
    cache.set(cache_key, result, get_health_cache_config()['health_cache_ttl'])
    return result


__all__ = [
    'CacheMeta',
    'TrackingDisabled',
    'fleet_cache_key',
    'get_fleet',
    'get_tracking_health',
    'get_vehicle',
    'tracking_enabled',
    'vehicle_cache_key',
]
