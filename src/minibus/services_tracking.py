"""Minibus live vehicle tracking — cached proxy to Eleven Systems AVL."""

from __future__ import annotations

from typing import Any

from decouple import config
from django.core.cache import cache
from django.utils import timezone

from minibus.tracking_client import (
    MINIBUS_TRACKING_BASE_URL,
    MinibusTrackingError,
    MinibusTrackingNotFoundError,
    fetch_fleet_locations,
    fetch_vehicle_location,
)
from shared.tracking_cache import CacheMeta, cached_fetch
from tenancy.models import Island

TRACKING_ATTRIBUTION = 'Live vehicle data via Eleven Systems (PDL Mini Bus)'
TRACKING_SOURCE_URL = 'https://tracking.elevensystems.pt/pdl'

CACHE_TTL_MIN = 1
CACHE_TTL_MAX = 300
STALE_GRACE_MAX = 600
LOCK_TTL_MAX = 30
HEALTH_CACHE_TTL_MIN = 5
HEALTH_CACHE_TTL_MAX = 120

__all__ = ['CacheMeta']


def get_tracking_config() -> dict[str, int]:
    # Also the client's poll cadence: it is echoed as `cacheMaxAgeSeconds` and
    # `minibusTrackingPollIntervalMs` polls at exactly that rate. A minute keeps
    # the map honest while cutting upstream traffic six-fold.
    cache_ttl = config('MINIBUS_TRACKING_CACHE_TTL', default=60, cast=int)
    # Must exceed cache_ttl, or the stale window is empty and a brief upstream
    # blip blanks the map rather than serving the last good fleet.
    stale_grace = config('MINIBUS_TRACKING_STALE_GRACE', default=180, cast=int)
    lock_ttl = config('MINIBUS_TRACKING_LOCK_TTL', default=5, cast=int)
    cache_ttl = max(CACHE_TTL_MIN, min(cache_ttl, CACHE_TTL_MAX))
    stale_grace = max(0, min(stale_grace, STALE_GRACE_MAX))
    lock_ttl = max(1, min(lock_ttl, LOCK_TTL_MAX))
    return {
        'cache_ttl': cache_ttl,
        'stale_grace': stale_grace,
        'lock_ttl': lock_ttl,
        'cache_max_age_seconds': cache_ttl,
    }


def get_fleet_tracking(island: Island) -> tuple[list[dict[str, Any]], CacheMeta]:
    cfg = get_tracking_config()
    cache_key = _fleet_cache_key(island.key)
    lock_key = _fleet_lock_key(island.key)
    return cached_fetch(
        cache_key=cache_key,
        lock_key=lock_key,
        fetch_fn=fetch_fleet_locations,
        cache_ttl=cfg['cache_ttl'],
        stale_grace=cfg['stale_grace'],
        lock_ttl=cfg['lock_ttl'],
        error_type=MinibusTrackingError,
    )


def get_vehicle_tracking(island: Island, tracking_id: str) -> tuple[dict[str, Any], CacheMeta]:
    cfg = get_tracking_config()
    cache_key = _vehicle_cache_key(island.key, tracking_id)
    lock_key = _vehicle_lock_key(island.key, tracking_id)
    return cached_fetch(
        cache_key=cache_key,
        lock_key=lock_key,
        fetch_fn=lambda: fetch_vehicle_location(tracking_id),
        cache_ttl=cfg['cache_ttl'],
        stale_grace=cfg['stale_grace'],
        lock_ttl=cfg['lock_ttl'],
        error_type=MinibusTrackingError,
    )


def get_health_cache_config() -> dict[str, int]:
    health_ttl = config('MINIBUS_TRACKING_HEALTH_CACHE_TTL', default=30, cast=int)
    health_ttl = max(HEALTH_CACHE_TTL_MIN, min(health_ttl, HEALTH_CACHE_TTL_MAX))
    return {
        'health_cache_ttl': health_ttl,
        'recheck_after_seconds': health_ttl,
    }


def get_tracking_health(island: Island, *, force: bool = False) -> dict[str, Any]:
    """Probe upstream AVL reachability; cache result separately from fleet snapshots."""
    cache_key = _health_cache_key(island.key)
    cfg = get_health_cache_config()

    if not force:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    result = _probe_tracking_health(cfg['recheck_after_seconds'])

    if not force:
        cache.set(cache_key, result, cfg['health_cache_ttl'])

    return result


def build_tracking_response_meta(meta: CacheMeta) -> dict[str, Any]:
    cfg = get_tracking_config()
    return {
        'cachedAt': meta.cached_at.isoformat(),
        'stale': meta.stale,
        'trackingCacheStatus': meta.cache_status,
        'cacheMaxAgeSeconds': cfg['cache_max_age_seconds'],
        'trackingAttribution': TRACKING_ATTRIBUTION,
        'trackingSourceUrl': TRACKING_SOURCE_URL,
        'trackingUpstreamBaseUrl': MINIBUS_TRACKING_BASE_URL,
    }


def _health_cache_key(island_key: str) -> str:
    return f'minibus:tracking:health:{island_key}'


def _probe_tracking_health(recheck_after_seconds: int) -> dict[str, Any]:
    checked_at = timezone.now().isoformat()
    try:
        fleet = fetch_fleet_locations()
        return {
            'available': True,
            'checkedAt': checked_at,
            'recheckAfterSeconds': recheck_after_seconds,
            'vehicleCount': len(fleet),
        }
    except MinibusTrackingError as exc:
        return {
            'available': False,
            'reason': _map_tracking_error_reason(exc),
            'checkedAt': checked_at,
            'recheckAfterSeconds': recheck_after_seconds,
        }


def _map_tracking_error_reason(exc: MinibusTrackingError) -> str:
    message = str(exc).lower()
    if '403' in message:
        return 'upstream_http_403'
    if '404' in message:
        return 'upstream_http_404'
    if 'timeout' in message or 'timed out' in message:
        return 'upstream_timeout'
    if any(token in message for token in ('connection', 'unreachable', 'network', 'refused')):
        return 'upstream_unreachable'
    return 'upstream_error'


def _fleet_cache_key(island_key: str) -> str:
    return f'minibus:tracking:fleet:{island_key}'


def _vehicle_cache_key(island_key: str, tracking_id: str) -> str:
    return f'minibus:tracking:vehicle:{island_key}:{tracking_id}'


def _fleet_lock_key(island_key: str) -> str:
    return f'minibus:tracking:lock:fleet:{island_key}'


def _vehicle_lock_key(island_key: str, tracking_id: str) -> str:
    return f'minibus:tracking:lock:vehicle:{island_key}:{tracking_id}'

