"""Minibus live vehicle tracking — cached proxy to Eleven Systems AVL."""

from __future__ import annotations

import time as _time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

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
from tenancy.models import Island

TRACKING_ATTRIBUTION = 'Live vehicle data via Eleven Systems (PDL Mini Bus)'
TRACKING_SOURCE_URL = 'https://tracking.elevensystems.pt/pdl'

CACHE_TTL_MIN = 1
CACHE_TTL_MAX = 300
STALE_GRACE_MAX = 600
LOCK_TTL_MAX = 30
LOCK_POLL_ATTEMPTS = 30
LOCK_POLL_INTERVAL = 0.1
HEALTH_CACHE_TTL_MIN = 5
HEALTH_CACHE_TTL_MAX = 120


@dataclass(frozen=True)
class CacheMeta:
    cached_at: datetime
    cache_status: str  # hit | miss | stale
    stale: bool = False


def get_tracking_config() -> dict[str, int]:
    cache_ttl = config('MINIBUS_TRACKING_CACHE_TTL', default=10, cast=int)
    stale_grace = config('MINIBUS_TRACKING_STALE_GRACE', default=60, cast=int)
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
    return _cached_fetch(
        cache_key=cache_key,
        lock_key=lock_key,
        fetch_fn=fetch_fleet_locations,
        cache_ttl=cfg['cache_ttl'],
        stale_grace=cfg['stale_grace'],
        lock_ttl=cfg['lock_ttl'],
    )


def get_vehicle_tracking(island: Island, tracking_id: str) -> tuple[dict[str, Any], CacheMeta]:
    cfg = get_tracking_config()
    cache_key = _vehicle_cache_key(island.key, tracking_id)
    lock_key = _vehicle_lock_key(island.key, tracking_id)
    return _cached_fetch(
        cache_key=cache_key,
        lock_key=lock_key,
        fetch_fn=lambda: fetch_vehicle_location(tracking_id),
        cache_ttl=cfg['cache_ttl'],
        stale_grace=cfg['stale_grace'],
        lock_ttl=cfg['lock_ttl'],
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


def _cached_fetch(
    *,
    cache_key: str,
    lock_key: str,
    fetch_fn: Callable[[], Any],
    cache_ttl: int,
    stale_grace: int,
    lock_ttl: int,
) -> tuple[Any, CacheMeta]:
    envelope = cache.get(cache_key)
    now = timezone.now()

    if envelope is not None:
        fetched_at = _parse_fetched_at(envelope['fetched_at'])
        age = (now - fetched_at).total_seconds()
        if age <= cache_ttl:
            return envelope['payload'], CacheMeta(
                cached_at=fetched_at,
                cache_status='hit',
                stale=False,
            )

    try:
        payload, fetched_at, cache_status = _refresh_with_lock(
            cache_key=cache_key,
            lock_key=lock_key,
            fetch_fn=fetch_fn,
            cache_ttl=cache_ttl,
            stale_grace=stale_grace,
            lock_ttl=lock_ttl,
        )
        return payload, CacheMeta(cached_at=fetched_at, cache_status=cache_status, stale=False)
    except MinibusTrackingError:
        if envelope is None:
            raise
        fetched_at = _parse_fetched_at(envelope['fetched_at'])
        age = (now - fetched_at).total_seconds()
        if age <= stale_grace:
            return envelope['payload'], CacheMeta(
                cached_at=fetched_at,
                cache_status='stale',
                stale=True,
            )
        raise


def _refresh_with_lock(
    *,
    cache_key: str,
    lock_key: str,
    fetch_fn: Callable[[], Any],
    cache_ttl: int,
    stale_grace: int,
    lock_ttl: int,
) -> tuple[Any, datetime, str]:
    if cache.add(lock_key, '1', lock_ttl):
        try:
            payload = fetch_fn()
            fetched_at = timezone.now()
            envelope = {'payload': payload, 'fetched_at': fetched_at.isoformat()}
            cache.set(cache_key, envelope, cache_ttl + stale_grace)
            return payload, fetched_at, 'miss'
        finally:
            cache.delete(lock_key)

    for _ in range(LOCK_POLL_ATTEMPTS):
        _time.sleep(LOCK_POLL_INTERVAL)
        envelope = cache.get(cache_key)
        if envelope is not None:
            fetched_at = _parse_fetched_at(envelope['fetched_at'])
            return envelope['payload'], fetched_at, 'miss'

    payload = fetch_fn()
    fetched_at = timezone.now()
    envelope = {'payload': payload, 'fetched_at': fetched_at.isoformat()}
    cache.set(cache_key, envelope, cache_ttl + stale_grace)
    return payload, fetched_at, 'miss'


def _parse_fetched_at(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed
