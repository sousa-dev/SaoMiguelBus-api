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


def _forward_cache_key(island_key: str) -> str:
    return f'azoresbus:tracking:forward:{island_key}'


def _stop_index_cache_key(island_key: str) -> str:
    return f'azoresbus:tracking:stopindex:{island_key}'


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
    """Fold sweep results into the ROUTE index. Small on purpose.

    Only what the fleet response needs: this blob is unpickled on every fleet
    poll, so the bulky forward-stop lists live in `merge_forward` under their
    own key instead.

    A failed lookup keeps whatever we already had.
    """
    merged = dict(index)
    stamp = now.isoformat()
    for vehicle_id, facts in results.items():
        if facts is None:
            continue
        merged[vehicle_id] = {
            'route': facts.get('route') or {},
            'journeyId': facts.get('journeyId', ''),
            'refreshed_at': stamp,
        }
    return merged


def merge_forward(
    forward_index: dict[str, dict],
    results: dict[str, dict | None],
    now: datetime,
) -> dict[str, dict]:
    """The same fold for the forward-stop lists, kept apart from the hot path."""
    merged = dict(forward_index)
    stamp = now.isoformat()
    for vehicle_id, facts in results.items():
        if facts is None:
            continue
        merged[vehicle_id] = {
            'forward': facts.get('forward') or [],
            'refreshed_at': stamp,
        }
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
    """What we keep from one vehicle's detail. Runs on a worker thread.

    The fetch pulls ~12KB whether we want it or not, and for a long time this
    function kept about eighty bytes of it. The forward stop list -- every stop
    still ahead of the bus, with its ETA -- comes out of the same response for
    no extra request and no extra byte, so we keep that too and invert it into
    the stop index.

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
    journey = raw.get('journey') or {}
    return {
        'route': serialize_route(route),
        'journeyId': str(journey.get('id', '')),
        'forward': forward_stops(journey.get('circulations') or []),
    }


def forward_stops(circulations: list[dict]) -> list[tuple[str, int]]:
    """`(stage_id, dueInMinutes)` for the stops still ahead of the bus.

    Upstream omits `dueInMinutes` for stops already passed, so its presence is
    the filter -- no need to compare against `currentStopSequence`.

    Anything beyond the horizon is dropped. A bus due in 170 minutes is
    technically 'coming', but listing it tells a waiting rider nothing and it
    triples the index for stops nobody is asking about.
    """
    horizon = clamp(
        config('AZORESBUS_TRACKING_ARRIVAL_HORIZON_MIN', default=60, cast=int),
        5, 240,
    )
    out: list[tuple[str, int]] = []
    for circulation in circulations:
        due = circulation.get('dueInMinutes')
        if due is None or due > horizon:
            continue
        stage_id = str((circulation.get('stage') or {}).get('id', ''))
        if stage_id:
            out.append((stage_id, int(due)))
    return out


def _sweep(vehicle_ids: list[str], cfg: dict[str, int]) -> dict[str, dict | None]:
    if not vehicle_ids:
        return {}

    results: dict[str, dict | None] = {}
    pool = ThreadPoolExecutor(max_workers=cfg['concurrency'])
    try:
        futures = {
            pool.submit(_fetch_route_for, vehicle_id): vehicle_id
            for vehicle_id in vehicle_ids
        }
        done, _pending = wait(futures.keys(), timeout=cfg['deadline'])
        for future in done:
            results[futures[future]] = future.result()
    finally:
    # NOT a `with` block: the context manager calls shutdown(wait=True) on
    # exit, which waits for every running future and silently defeats the
    # timeout above. Anything still in flight is left to finish in the
    # background -- its result still lands in the per-vehicle cache, so the work
    # is not wasted, it just stops holding the request open.
        pool.shutdown(wait=False, cancel_futures=True)
    return results


def invert_to_stop_index(
    index: dict[str, dict],
    forward_index: dict[str, dict],
) -> dict[str, list[dict]]:
    """`{stage_id: [{vehicleId, dueInMinutes, ...}]}`, soonest first.

    Pure, so the shape can be tested without a sweep or a cache.
    """
    by_stop: dict[str, list[dict]] = {}
    for vehicle_id, entry in forward_index.items():
        route = (index.get(vehicle_id) or {}).get('route') or {}
        captured_at = entry.get('refreshed_at', '')
        for stage_id, due in entry.get('forward') or []:
            by_stop.setdefault(stage_id, []).append({
                'vehicleId': vehicle_id,
                'dueInMinutes': due,
                'routeId': route.get('id', ''),
                'lineCode': route.get('nameShort', ''),
                'journeyId': (index.get(vehicle_id) or {}).get('journeyId', ''),
                # When this ETA was captured, so the reader can age-compensate.
                'capturedAt': captured_at,
            })
    for arrivals in by_stop.values():
        arrivals.sort(key=lambda row: row['dueInMinutes'])
    return by_stop


def stop_index(island) -> dict[str, list[dict]]:
    """The inverted index, or empty when no sweep has run yet."""
    return cache.get(_stop_index_cache_key(island.key)) or {}


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
        results = _sweep(pending[:cfg['batch']], cfg)
        index = prune_index(
            merge_index(index, results, now), vehicle_ids, cfg['index_grace'], now,
        )
        ttl = cfg['index_ttl'] + cfg['index_grace']
        cache.set(cache_key, index, ttl)

        # SEPARATE keys, deliberately. The forward-stop lists are a couple of
        # hundred kilobytes and only the arrivals endpoint reads them, whereas
        # the route index above is unpickled on every fleet poll -- roughly
        # every ten seconds, per process -- to look up eighty bytes of route.
        # Merging them would make the common path pay for the rare one.
        forward_index = prune_index(
            merge_forward(cache.get(_forward_cache_key(island.key)) or {}, results, now),
            vehicle_ids,
            cfg['index_grace'],
            now,
        )
        cache.set(_forward_cache_key(island.key), forward_index, ttl)
        cache.set(
            _stop_index_cache_key(island.key),
            invert_to_stop_index(index, forward_index),
            ttl,
        )

    for vehicle in vehicles:
        entry = index.get(vehicle.get('id'))
        route = entry.get('route') if entry else None
        vehicle['route'] = route or None
    return vehicles
