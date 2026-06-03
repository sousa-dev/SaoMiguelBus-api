"""Offline transit bundle serialization + data-revision staleness signal.

The mobile client downloads a single self-contained bundle for offline route
search. ``data_revision`` is a write-triggered counter (bumped by model signals
on any schedule-bearing change) that gives a deterministic staleness signal
without hashing the whole dataset on every request.
"""

from __future__ import annotations

import contextlib
import contextvars
import hashlib
import time as _time

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from tenancy.models import Island
from tenancy.services import for_island
from transit.models import Holiday, Stop, Trip
from transit.services.compat import _serialize_active_infos, _trip_to_load_route
from transit.services.v3 import serialize_stops_v3

_REVISION_FLAG = 'data_revision'

_BUNDLE_CACHE_TTL = 24 * 3600
_BUNDLE_LOCK_TTL = 30

# Set during bulk imports so per-row writes do not each trigger a revision bump;
# callers issue a single bump after the import completes.
_suppress_bumps: contextvars.ContextVar[bool] = contextvars.ContextVar(
    'transit_suppress_revision_bumps', default=False
)


@contextlib.contextmanager
def suppress_revision_bumps():
    token = _suppress_bumps.set(True)
    try:
        yield
    finally:
        _suppress_bumps.reset(token)


def revision_bumps_suppressed() -> bool:
    return _suppress_bumps.get()


def get_data_revision(island: Island) -> int:
    flags = island.feature_flags or {}
    try:
        return int(flags.get(_REVISION_FLAG, 0))
    except (TypeError, ValueError):
        return 0


def bump_data_revision(island_id: int) -> int:
    """Atomically increment the island's transit data revision.

    Low-concurrency path (admin edits / end-of-import), so a select-for-update
    read-modify-write on the ``feature_flags`` JSON is acceptable.
    """
    with transaction.atomic():
        island = Island.objects.select_for_update().get(pk=island_id)
        flags = dict(island.feature_flags or {})
        try:
            current = int(flags.get(_REVISION_FLAG, 0))
        except (TypeError, ValueError):
            current = 0
        next_revision = current + 1
        flags[_REVISION_FLAG] = next_revision
        island.feature_flags = flags
        island.save(update_fields=['feature_flags', 'updated_at'])
    return next_revision


def compute_bundle_version(island: Island) -> str:
    """Deterministic version fingerprint for the offline bundle.

    Folds the write-triggered revision together with cheap row counts so that
    the fingerprint changes on any schedule mutation even if a revision write
    was somehow missed.
    """
    revision = get_data_revision(island)
    stops_count = Stop.objects.count()
    routes_count = Trip.objects.filter(source=Trip.SOURCE_OPERATOR).count()
    raw = f'{island.key}:{revision}:{stops_count}:{routes_count}'
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]


def build_offline_bundle(island: Island) -> dict:
    """Self-contained transit dataset for offline route search."""
    holidays = [
        {'id': h.id, 'date': h.date.isoformat(), 'name': h.name}
        for h in Holiday.objects.all().order_by('date')
    ]
    stops = serialize_stops_v3(Stop.objects.all().order_by('name'))
    trips = (
        Trip.objects.filter(source=Trip.SOURCE_OPERATOR)
        .select_related('line', 'calendar')
        .exclude(line__disabled=True)
    )
    routes = [_trip_to_load_route(trip) for trip in trips]
    flags = island.feature_flags or {}
    return {
        'version': compute_bundle_version(island),
        'generatedAt': timezone.now().isoformat(),
        'island': island.key,
        'maps': flags.get('maps', False),
        'counts': {'stops': Stop.objects.count(), 'routes': len(routes)},
        'stops': stops,
        'holidays': holidays,
        'infos': _serialize_active_infos(),
        'routes': routes,
    }


def _bundle_cache_key(island_key: str, version: str) -> str:
    return f'transit:offline:bundle:{island_key}:{version}'


def get_offline_bundle_cached(island: Island) -> dict:
    """Return the offline bundle, served from Redis when warm.

    Keyed by version: a data change produces a new version (cache miss → rebuild)
    while stale entries expire naturally. A single-flight lock prevents a rebuild
    stampede when many clients request a cold version at once.
    """
    with for_island(island):
        version = compute_bundle_version(island)
        cache_key = _bundle_cache_key(island.key, version)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        lock_key = f'transit:offline:lock:{island.key}'
        if cache.add(lock_key, '1', _BUNDLE_LOCK_TTL):
            try:
                bundle = build_offline_bundle(island)
                cache.set(cache_key, bundle, _BUNDLE_CACHE_TTL)
                return bundle
            finally:
                cache.delete(lock_key)

        # Another worker is building; briefly wait for it to populate the cache.
        for _ in range(30):
            _time.sleep(0.1)
            cached = cache.get(cache_key)
            if cached is not None:
                return cached
        # Fallback: build without caching rather than block the client.
        return build_offline_bundle(island)


def prewarm_offline_bundle(island: Island) -> None:
    """Best-effort cache warmup (e.g. after a bulk import)."""
    try:
        get_offline_bundle_cached(island)
    except Exception:  # pragma: no cover - warmup must never break the caller
        pass
