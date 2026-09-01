"""Turning a live vehicle's stops into places we already know about.

The AVL feed names stops in the operator's own shorthand -- `P. DELGADA
(ALFÂNDEGA)`, `FURNAS (PQ. CAMPISMO)` -- while everywhere else in the app shows
the canonical names the importer produced. The two must agree, or a rider
comparing a live bus against a timetable sees two different places.

The tempting fix is to run `services_names.canonicalize` over the live name,
since it is a pure function sitting right there. Measured against a real
67-circulation capture, that resolves 48 of 67 and, worse, invents names that
look right:

    live 'S. BRÁS (R. TOMÉ V. PACHECO)'  ->  canonicalize: 'Tomé Vila Pacheco'
                                             truth:        'Tomé Vaz Pacheco'

`V.` expands to `Vila` by the abbreviation table; upstream meant `Vaz`. The
schedules feed spells it out so the importer never hits the trap, and the live
feed abbreviates so a live-side canonicalise always does. A miss is recoverable.
A confident wrong answer is not.

Worse still, the two feeds genuinely disagree for 23 of those 67 stops -- same
pole id, different name (`CASA DE GALO` upstream is `Porto Formoso (Canada de
Galo)` to us). No function bridges that.

So we do not transform the name at all. We join on `stage.id`, which the
importer already stored as `ExternalStop.external_id` against the real
`transit.Stop`. That resolves 66 of 67; the one miss is a stop added upstream
after the last sync, which correctly falls back to its raw name.
"""

from __future__ import annotations

import logging

from django.core.cache import cache

from azoresbus.models import ExternalStop
from transit.models import DATASET_AZORESBUS

logger = logging.getLogger(__name__)

# The table only changes when `sync_azoresbus` runs, so this can be held for a
# long time; the sync is what should invalidate it, not the clock.
IDENTITY_TTL = 6 * 60 * 60


def _cache_key(island_key: str) -> str:
    return f'azoresbus:stops:identity:{island_key}'


def stop_identity_map(island) -> dict[str, dict]:
    """`{external_id: {'stopId': int, 'name': str}}` for the whole island.

    1456 poles collapsing to 814 stops is ~100KB held whole, which is cheaper
    than an IN query per vehicle detail and far cheaper than one per stop.
    """
    cache_key = _cache_key(island.key)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    rows = (
        ExternalStop.objects
        .filter(island=island, dataset=DATASET_AZORESBUS)
        .select_related('stop')
        .values_list('external_id', 'stop_id', 'stop__name')
    )
    identity = {
        str(external_id): {'stopId': stop_id, 'name': stop_name}
        for external_id, stop_id, stop_name in rows
    }

    cache.set(cache_key, identity, IDENTITY_TTL)
    return identity


def safe_stop_identity_map(island) -> dict[str, dict]:
    """As above, but a database problem costs us names rather than the fleet."""
    try:
        return stop_identity_map(island)
    except Exception:  # noqa: BLE001 - a live map with raw names still works
        logger.exception('azoresbus stop identity unavailable; using raw names')
        return {}


def invalidate_stop_identity(island_key: str) -> None:
    """Call after a sync rewrites the stop tables."""
    cache.delete(_cache_key(island_key))
