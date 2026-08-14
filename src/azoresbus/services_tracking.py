"""Cached, flag-gated access to the AzoresBus fleet.

Three distinct states, and conflating them is the easy mistake (02 §8):

    tracking_disabled   the feature flag is off        -> 503
    empty fleet         nobody is reporting            -> 200 []
    upstream failure    the AVL API is down            -> 502

Mirrors minibus/services_tracking.py: short TTL cache, stale-grace fallback so a
brief upstream blip does not blank the map.
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
from transit.services.schedule_phase import azoresbus_flags

logger = logging.getLogger(__name__)

CACHE_TTL = config('AZORESBUS_TRACKING_CACHE_TTL', default=10, cast=int)
STALE_GRACE = config('AZORESBUS_TRACKING_STALE_GRACE', default=60, cast=int)

FLEET_KEY = 'azoresbus:tracking:fleet'
FLEET_STALE_KEY = 'azoresbus:tracking:fleet:stale'


class TrackingDisabled(Exception):
    """The feature flag is off. Not an error, a configuration."""


def tracking_enabled(island) -> bool:
    return bool(azoresbus_flags(island).get('trackingEnabled', False))


def get_fleet(island) -> list[dict]:
    if not tracking_enabled(island):
        raise TrackingDisabled('tracking_disabled')

    cached = cache.get(FLEET_KEY)
    if cached is not None:
        return cached

    try:
        raw = fetch_fleet_locations()
    except AzoresbusTrackingError:
        stale = cache.get(FLEET_STALE_KEY)
        if stale is not None:
            logger.warning('azoresbus fleet upstream failed; serving stale')
            return stale
        raise

    vehicles = [serialize_fleet_vehicle(item) for item in raw]
    cache.set(FLEET_KEY, vehicles, CACHE_TTL)
    cache.set(FLEET_STALE_KEY, vehicles, STALE_GRACE)
    return vehicles


def get_vehicle(island, vehicle_id: str) -> dict:
    if not tracking_enabled(island):
        raise TrackingDisabled('tracking_disabled')
    return serialize_vehicle_detail(fetch_vehicle_location(vehicle_id))
