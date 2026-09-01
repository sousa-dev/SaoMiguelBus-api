"""Which line is each bus on?

The AVL list endpoint does not say. It returns `{id, position, speed, status,
color, busStatus, delay}` and nothing else, `?routeId=` filters server-side but
cannot be inverted into "which route is this vehicle on", and `color` is a
service class -- 49 of the 56 routes share `2D59A9`. The only place the answer
exists is each vehicle's own detail payload.

Fanning that out per request would be 40 upstream calls every 10s, each ~10KB,
through the Tailscale Pi that Cloudflare forces us to egress through
(`shared/upstream_proxy.py`). Instead we keep a ROUTE INDEX -- vehicle id to
route -- refreshed by a bounded sweep at most once per `SWEEP_INTERVAL`, and
serve the fleet from whatever the index currently knows.

Two properties this file exists to guarantee:

  * a sweep never blocks a request longer than `FANOUT_DEADLINE`. Whatever
    finished is merged; the rest are picked up by the next sweep. A cold index
    converges over one or two polls rather than stalling the first one.
  * a sweep can never fail a request. Every per-vehicle error is swallowed and
    the previous entry retained, because a fleet with no line labels is still a
    working map, and a 502 is not.

A vehicle's route changes only when it starts a new journey, so entries are good
for minutes, not seconds -- which is what makes the whole approach affordable.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta

from decouple import config
from django.core.cache import cache
from django.utils import timezone

from azoresbus.tracking_client import (
    AzoresbusTrackingError,
    fetch_routes,
    fetch_vehicle_location,
    serialize_route,
)
from shared.tracking_cache import clamp

logger = logging.getLogger(__name__)

CATALOGUE_TTL = 6 * 60 * 60


def _settings() -> dict[str, int]:
    return {
        'index_ttl': clamp(
            config('AZORESBUS_TRACKING_ROUTE_INDEX_TTL', default=180, cast=int),
            30, 900,
        ),
        'index_grace': clamp(
            config('AZORESBUS_TRACKING_ROUTE_INDEX_GRACE', default=1800, cast=int),
            0, 7200,
        ),
        'sweep_interval': clamp(
            config('AZORESBUS_TRACKING_SWEEP_INTERVAL', default=30, cast=int),
            10, 300,
        ),
        'concurrency': clamp(
            config('AZORESBUS_TRACKING_FANOUT_CONCURRENCY', default=6, cast=int),
            1, 12,
        ),
        'deadline': clamp(
            config('AZORESBUS_TRACKING_FANOUT_DEADLINE', default=6, cast=int),
            2, 30,
        ),
        'batch': clamp(
            config('AZORESBUS_TRACKING_FANOUT_BATCH', default=40, cast=int),
            1, 200,
        ),
    }


def _index_cache_key(island_key: str) -> str:
    return f'azoresbus:tracking:routeindex:{island_key}'


def _sweep_lock_key(island_key: str) -> str:
    return f'azoresbus:tracking:routeindex:sweep:{island_key}'


def _catalogue_cache_key(island_key: str) -> str:
    return f'azoresbus:tracking:routes:{island_key}'


def route_catalogue(island) -> dict[str, dict]:
    """`{route_id: route}` for the whole network. ~6KB, effectively static."""
    cache_key = _catalogue_cache_key(island.key)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        routes = {
            str(raw.get('id', '')): serialize_route(raw)
            for raw in fetch_routes()
        }
    except AzoresbusTrackingError:
        logger.warning('azoresbus route catalogue unavailable')
        return {}

    cache.set(cache_key, routes, CATALOGUE_TTL)
    return routes


def stale_ids(
    index: dict[str, dict],
    vehicle_ids: list[str],
    ttl_seconds: int,
    now: datetime,
) -> list[str]:
    """Which vehicles need a detail fetch, never-seen ones first.

    Ordering matters under a deadline: a vehicle with no entry shows no line at
    all, while a vehicle with a stale entry still shows the right one nearly
    always. Pure, so the policy is testable without touching HTTP or the cache.
    """
    missing: list[str] = []
    expired: list[tuple[datetime, str]] = []

    for vehicle_id in vehicle_ids:
        entry = index.get(vehicle_id)
        if not entry or not entry.get('refreshed_at'):
            missing.append(vehicle_id)
            continue
        try:
            refreshed_at = datetime.fromisoformat(entry['refreshed_at'])
        except (TypeError, ValueError):
            missing.append(vehicle_id)
            continue
        if (now - refreshed_at).total_seconds() > ttl_seconds:
            expired.append((refreshed_at, vehicle_id))

    expired.sort()  # oldest first
    return missing + [vehicle_id for _refreshed_at, vehicle_id in expired]


def merge_index(
    index: dict[str, dict],
    results: dict[str, dict | None],
    now: datetime,
) -> dict[str, dict]:
    """Fold sweep results in. A failed lookup keeps whatever we already had."""
    merged = dict(index)
    stamp = now.isoformat()
    for vehicle_id, route in results.items():
        if route is None:
            continue
        merged[vehicle_id] = {'route': route, 'refreshed_at': stamp}
    return merged


def prune_index(
    index: dict[str, dict],
    vehicle_ids: list[str],
    grace_seconds: int,
    now: datetime,
) -> dict[str, dict]:
    """Drop entries for buses that left service long enough ago to stay gone.

    The fleet churns all day (41 vehicles at noon, 29 an hour later), so without
    this the index grows forever with the day's retired buses.
    """
    live = set(vehicle_ids)
    cutoff = now - timedelta(seconds=grace_seconds)
    kept: dict[str, dict] = {}
    for vehicle_id, entry in index.items():
        if vehicle_id in live:
            kept[vehicle_id] = entry
            continue
        try:
            refreshed_at = datetime.fromisoformat(entry.get('refreshed_at', ''))
        except (TypeError, ValueError):
            continue
        if refreshed_at >= cutoff:
            kept[vehicle_id] = entry
    return kept


def _fetch_route_for(vehicle_id: str) -> dict | None:
    """Detail fetch reduced to just the route. Runs on a worker thread.

    Touches no ORM and no request state, which is why it needs no `for_island`
    context -- do not add a query here without revisiting that.
    """
    try:
        raw = fetch_vehicle_location(vehicle_id)
    except AzoresbusTrackingError:
        return None
    except Exception:  # noqa: BLE001 - a worker must never take down the sweep
        logger.exception('azoresbus route lookup failed id=%s', vehicle_id)
        return None
    route = raw.get('route') or {}
    if not route.get('id'):
        return None
    return serialize_route(route)


def _sweep(vehicle_ids: list[str], cfg: dict[str, int]) -> dict[str, dict | None]:
    if not vehicle_ids:
        return {}

    results: dict[str, dict | None] = {}
    with ThreadPoolExecutor(max_workers=cfg['concurrency']) as pool:
        futures = {
            pool.submit(_fetch_route_for, vehicle_id): vehicle_id
            for vehicle_id in vehicle_ids
        }
        done, pending = wait(futures.keys(), timeout=cfg['deadline'])
        for future in done:
            results[futures[future]] = future.result()
        for future in pending:
            # Left to finish in the background; next sweep will ask again.
            future.cancel()
    return results


def enrich_fleet(island, vehicles: list[dict]) -> list[dict]:
    """Attach `route` to each vehicle, sweeping for what we do not know yet."""
    cfg = _settings()
    now = timezone.now()
    vehicle_ids = [v['id'] for v in vehicles if v.get('id')]

    cache_key = _index_cache_key(island.key)
    index = cache.get(cache_key) or {}

    pending = stale_ids(index, vehicle_ids, cfg['index_ttl'], now)
    if pending and cache.add(
        _sweep_lock_key(island.key), '1', cfg['sweep_interval'],
    ):
        # The lock is never deleted on completion: letting it expire is what
        # turns it into a rate limit as well as a mutex.
        index = merge_index(index, _sweep(pending[:cfg['batch']], cfg), now)
        index = prune_index(index, vehicle_ids, cfg['index_grace'], now)
        cache.set(cache_key, index, cfg['index_ttl'] + cfg['index_grace'])

    for vehicle in vehicles:
        entry = index.get(vehicle.get('id'))
        vehicle['route'] = entry['route'] if entry else None
    return vehicles
