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
from datetime import datetime

from django.utils import timezone

from azoresbus.models import ExternalStop
from azoresbus.services_route_index import stop_index
from azoresbus.services_tracking import get_vehicle
from azoresbus.tracking_client import AzoresbusTrackingError
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


def _fresh_due(island, vehicle_id: str, stage_ids: set[str]) -> tuple[int | None, dict]:
    """Re-read this vehicle's ETA for the stop, straight from its detail.

    Goes through `get_vehicle`, so it rides the existing 10s per-vehicle cache:
    two riders watching the same stop cost one upstream call, not two.
    """
    detail = get_vehicle(island, vehicle_id)
    for circulation in detail.get('journey', {}).get('circulations') or []:
        stage = circulation.get('stage') or {}
        if str(stage.get('id')) in stage_ids and circulation.get('dueInMinutes') is not None:
            return int(circulation['dueInMinutes']), detail
    # The bus passed the stop between the sweep and now.
    return None, detail


def stop_arrivals(island, stop_id: int) -> list[dict]:
    """Inbound buses for one stop, soonest first."""
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
    arrivals: list[dict] = []
    for vehicle_id, row in candidates.items():
        try:
            fresh, detail = _fresh_due(island, vehicle_id, stage_ids)
        except AzoresbusTrackingError:
            # Fall back to the swept value rather than dropping a real bus.
            logger.warning('azoresbus arrival refresh failed id=%s', vehicle_id)
            fresh, detail = None, {}
            stale = True
        else:
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
