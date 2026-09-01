"""Which live buses are heading to a given stop, and how soon.

Two tiers, because the two halves of the answer age at completely different
rates:

  * WHICH buses -- changes only when a vehicle starts a new journey, so it comes
    free from the route-index sweep that is already running.
  * HOW SOON -- decrements about once a minute, so a three-minute-old number is
    a missed bus. That half is fetched on demand, for the one or two vehicles
    actually serving the stop somebody opened.

Measured on the live fleet, a stop has 1.3 inbound buses on average. Refreshing
those handful on a user's tap costs one or two upstream calls, deduped by the
per-vehicle cache that already exists -- against ~1500 ETAs island-wide, of which
almost none are ever looked at. That asymmetry is the whole design.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime

from decouple import config
from django.utils import timezone

from azoresbus.models import ExternalStop
from azoresbus.services_route_index import stop_index
from azoresbus.services_tracking import (
    TrackingDisabled,
    get_vehicle_raw,
    tracking_enabled,
)
from azoresbus.tracking_client import AzoresbusTrackingError
from shared.tracking_cache import clamp
from transit.models import DATASET_AZORESBUS

logger = logging.getLogger(__name__)


def stage_ids_for_stop(island, stop_id: int) -> list[str]:
    """A stop is one place; upstream splits it into a pole per direction."""
    return [
        str(external_id)
        for external_id in ExternalStop.objects
        .filter(island=island, dataset=DATASET_AZORESBUS, stop_id=stop_id)
        .values_list('external_id', flat=True)
    ]


def age_compensated(due_minutes: int, captured_at: str, now: datetime) -> int | None:
    """Discount a cached ETA by how long we have been sitting on it.

    `dueInMinutes` decrements roughly with the clock while a bus is moving, so
    subtracting the age recovers most of the staleness for free. It over-states
    the remaining time when the bus is held at a stop -- which is exactly the
    case where a precise number should not be trusted anyway, and why the caller
    marks these `stale`.
    """
    if not captured_at:
        return due_minutes
    try:
        captured = datetime.fromisoformat(captured_at)
    except (TypeError, ValueError):
        return due_minutes
    age_minutes = round((now - captured).total_seconds() / 60)
    return max(0, due_minutes - age_minutes)


def _refresh_deadline() -> int:
    """Wall-clock budget for the whole refresh, not per vehicle.

    This endpoint holds a worker while it waits on upstream, so an unbounded
    wait here queues every other request behind it -- a slow arrivals lookup
    was measurably delaying the stop page's own detail call. Better a couple of
    age-compensated estimates than a page that will not load.
    """
    return clamp(config('AZORESBUS_ARRIVALS_DEADLINE', default=4, cast=int), 1, 20)


def _fresh_due(island_key: str, vehicle_id: str, stage_ids: set[str]) -> tuple[int | None, dict]:
    """Re-read this vehicle's ETA for the stop, straight from its detail.

    Goes through the cached raw accessor, so it rides the existing per-vehicle
    cache -- two riders watching the same stop cost one upstream call -- and
    touches no ORM, which is what makes it safe on a worker thread.
    """
    detail = get_vehicle_raw(island_key, vehicle_id)
    for circulation in detail.get('journey', {}).get('circulations') or []:
        stage = circulation.get('stage') or {}
        if str(stage.get('id')) in stage_ids and circulation.get('dueInMinutes') is not None:
            return int(circulation['dueInMinutes']), detail
    # The bus passed the stop between the sweep and now.
    return None, detail


def _refresh_candidates(
    island_key: str,
    vehicle_ids: list[str],
    stage_ids: set[str],
) -> dict[str, tuple[int | None, dict] | None]:
    """Re-read every candidate at once, within one shared deadline.

    Sequentially this was N upstream round trips through the proxy; in parallel
    it is one. Anything still outstanding when the deadline passes is reported
    from the index instead, so latency is bounded by the deadline rather than by
    how many buses happen to serve the stop.
    """
    results: dict[str, tuple[int | None, dict] | None] = {}
    if not vehicle_ids:
        return results

    pool = ThreadPoolExecutor(max_workers=min(len(vehicle_ids), 6))
    try:
        futures = {
            pool.submit(_fresh_due, island_key, vehicle_id, stage_ids): vehicle_id
            for vehicle_id in vehicle_ids
        }
        done, _pending = wait(futures.keys(), timeout=_refresh_deadline())
        for future in done:
            vehicle_id = futures[future]
            try:
                results[vehicle_id] = future.result()
            except AzoresbusTrackingError:
                logger.warning('azoresbus arrival refresh failed id=%s', vehicle_id)
                results[vehicle_id] = None
            except Exception:  # noqa: BLE001 - one bad bus must not fail the stop
                logger.exception('azoresbus arrival refresh error id=%s', vehicle_id)
                results[vehicle_id] = None
    finally:
    # NOT a `with` block: the context manager calls shutdown(wait=True) on
    # exit, which waits for every running future and silently defeats the
    # timeout above. Anything still in flight is left to finish in the
    # background -- its result still lands in the per-vehicle cache, so the work
    # is not wasted, it just stops holding the request open.
        pool.shutdown(wait=False, cancel_futures=True)
    return results


def stop_arrivals(island, stop_id: int) -> list[dict]:
    """Inbound buses for one stop, soonest first."""
    # Checked here rather than inherited from `get_vehicle`: this path uses the
    # raw, thread-safe accessor, which deliberately carries no flag check. The
    # flag is how the feature gets retired without an app release, so it has to
    # hold on every entry point, not just the one that happens to check.
    if not tracking_enabled(island):
        raise TrackingDisabled('tracking_disabled')

    stage_ids = set(stage_ids_for_stop(island, stop_id))
    if not stage_ids:
        return []

    index = stop_index(island)
    candidates: dict[str, dict] = {}
    for stage_id in stage_ids:
        for row in index.get(stage_id, []):
            # A vehicle can serve both poles of a stop; keep its soonest.
            current = candidates.get(row['vehicleId'])
            if current is None or row['dueInMinutes'] < current['dueInMinutes']:
                candidates[row['vehicleId']] = row

    now = timezone.now()
    refreshed = _refresh_candidates(island.key, list(candidates), stage_ids)

    arrivals: list[dict] = []
    for vehicle_id, row in candidates.items():
        result = refreshed.get(vehicle_id)
        if result is None:
            # Unreachable, or still in flight when the deadline passed. Fall
            # back to the swept value rather than dropping a real bus.
            fresh, detail, stale = None, {}, True
        else:
            fresh, detail = result
            stale = False
            if fresh is None:
                # Detail was readable and the stop is no longer ahead of it:
                # the bus has been past. Drop it rather than show a stale ETA.
                continue

        due = (
            fresh
            if fresh is not None
            else age_compensated(row['dueInMinutes'], row.get('capturedAt', ''), now)
        )
        if due is None:
            continue

        route = detail.get('route') or {}
        arrivals.append({
            'vehicleId': vehicle_id,
            'dueInMinutes': due,
            'lineCode': route.get('nameShort') or row.get('lineCode', ''),
            'lineName': route.get('name', ''),
            'lineColor': route.get('color', ''),
            'journeyId': str(detail.get('journey', {}).get('id') or row.get('journeyId', '')),
            'stale': stale,
        })

    arrivals.sort(key=lambda row: row['dueInMinutes'])
    return arrivals
