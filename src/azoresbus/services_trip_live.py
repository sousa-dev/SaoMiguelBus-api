"""Which live bus is running a given Trip, and where it is.

The tracked-journey widget in the app interpolates a position from the
timetable and says so. This is the feed that lets it stop saying so: the AVL
detail for a vehicle carries `journey.id`, the schedule importer stores that
same id on `ExternalJourney.external_id`, and the route-index sweep already
caches it per vehicle. Trip -> journey id -> vehicle is therefore a lookup, not
a geometric guess.

Two things the index cannot be trusted for on its own, both handled here:

  * it refreshes every few minutes, so a bus that just finished journey A and
    started B can still be filed under A. The per-vehicle detail (cached for a
    minute) is re-read and its `journey.id` must agree, or the match is dropped
    -- a bus on the wrong trip is worse than no bus.
  * it only knows vehicles the sweep has reached; a cold index answers
    `not_found` rather than blocking, and converges within a poll or two.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, wait

from decouple import config
from django.core.cache import cache

from azoresbus.models import ExternalJourney
from azoresbus.services_route_index import route_index
from azoresbus.services_stop_identity import safe_stop_identity_map
from azoresbus.services_tracking import (
    TrackingDisabled,
    fleet_cache_key,
    get_fleet,
    get_vehicle_raw,
    tracking_enabled,
)
from azoresbus.tracking_client import AzoresbusTrackingError
from shared.tracking_cache import clamp
from transit.models import DATASET_AZORESBUS

logger = logging.getLogger(__name__)

MAX_TRIP_IDS = 5
STATE_LIVE = 'live'
STATE_NOT_FOUND = 'not_found'      # nobody in service reports this journey
STATE_UNSUPPORTED = 'unsupported'  # no upstream journey for this trip (legacy)


def parse_trip_ids(raw: str | None) -> list[int]:
    """Comma-separated ids, deduped in order, junk dropped, capped.

    A tracked itinerary has at most a couple of legs, so five is generous; the
    cap bounds the detail fan-out below, not the client.
    """
    out: list[int] = []
    for token in (raw or '').split(','):
        token = token.strip()
        if token.isdigit():
            value = int(token)
            if value not in out:
                out.append(value)
    return out[:MAX_TRIP_IDS]


def match_vehicles(
    index: dict[str, dict],
    live_vehicle_ids,
    journey_ids,
) -> dict[str, str]:
    """`{journey_id: vehicle_id}` for the journeys a bus in service is on.

    Restricted to the current fleet so a retired bus's stale index entry (kept
    for the grace window) cannot claim a trip.
    """
    wanted = {str(j) for j in journey_ids}
    live = {str(v) for v in live_vehicle_ids}
    matches: dict[str, str] = {}
    for vehicle_id, entry in index.items():
        journey_id = str((entry or {}).get('journeyId') or '')
        if vehicle_id in live and journey_id in wanted and journey_id not in matches:
            matches[journey_id] = vehicle_id
    return matches


def upcoming_stops_from_detail(raw: dict, stop_identity: dict[str, dict] | None) -> list[dict]:
    """Every stop still ahead of the bus, nearest first.

    Upstream omits `dueInMinutes` for stops already passed, so its presence is
    the filter (same rule as `services_route_index.forward_stops`). Kept as the
    whole list, not just the nearest one, so the app's trip detail page can show
    a live ETA against every remaining stop rather than only the next one.
    """
    circulations = (raw.get('journey') or {}).get('circulations') or []
    ahead = [c for c in circulations if c.get('dueInMinutes') is not None]
    out: list[dict] = []
    for circulation in sorted(ahead, key=lambda c: int(c.get('sequence') or 0)):
        stage = circulation.get('stage') or {}
        identity = (stop_identity or {}).get(str(stage.get('id')), {})
        out.append({
            'sequence': circulation.get('sequence'),
            'name': identity.get('name') or stage.get('name', ''),
            'stopId': identity.get('stopId'),
            'dueInMinutes': int(circulation['dueInMinutes']),
        })
    return out


def next_stop_from_detail(raw: dict, stop_identity: dict[str, dict] | None) -> dict | None:
    """The first stop still ahead of the bus."""
    upcoming = upcoming_stops_from_detail(raw, stop_identity)
    return upcoming[0] if upcoming else None


def serialize_live_vehicle(
    fleet_item: dict,
    raw: dict,
    captured_at: str,
    upcoming_stops: list[dict],
    *,
    stale: bool,
) -> dict:
    """Position from the fleet list (refreshed on every call); progress from the detail.

    `delay` lives only on the list; movement `status` and the stop sequence only
    on the detail. `stale` means the detail could not be read this time, so the
    position is real but the sequence and stop ETAs are unknown.
    """
    return {
        'id': str(raw.get('id') or fleet_item.get('id', '')),
        'position': fleet_item.get('position') or raw.get('position') or {},
        'delaySeconds': fleet_item.get('delay'),
        'speed': raw.get('speed'),
        'status': raw.get('status', ''),
        'currentStopSequence': raw.get('currentStopSequence'),
        'nextStop': upcoming_stops[0] if upcoming_stops else None,
        'upcomingStops': upcoming_stops,
        'capturedAt': captured_at,
        'stale': stale,
    }


def _detail_deadline() -> int:
    """Wall-clock budget for all detail reads, not per vehicle (same reasoning
    as `services_arrivals._refresh_deadline`: a slow upstream must not hold a
    worker hostage)."""
    return clamp(config('AZORESBUS_TRIP_LIVE_DEADLINE', default=4, cast=int), 1, 20)


def _read_details(island_key: str, vehicle_ids: list[str]) -> dict[str, dict | None]:
    """Cached per-vehicle detail for each id, in parallel, within one deadline.

    `None` for anything unreadable or still in flight at the deadline. Uses the
    ORM-free raw accessor so it is safe on worker threads.
    """
    results: dict[str, dict | None] = {vehicle_id: None for vehicle_id in vehicle_ids}
    if not vehicle_ids:
        return results
    pool = ThreadPoolExecutor(max_workers=min(len(vehicle_ids), 5))
    try:
        futures = {
            pool.submit(get_vehicle_raw, island_key, vehicle_id): vehicle_id
            for vehicle_id in vehicle_ids
        }
        done, _pending = wait(futures.keys(), timeout=_detail_deadline())
        for future in done:
            vehicle_id = futures[future]
            try:
                results[vehicle_id] = future.result()
            except AzoresbusTrackingError:
                logger.warning('azoresbus trip-live detail failed id=%s', vehicle_id)
            except Exception:  # noqa: BLE001 - one bad bus must not fail the trip
                logger.exception('azoresbus trip-live detail error id=%s', vehicle_id)
    finally:
        # Not a `with` block: shutdown(wait=True) would defeat the deadline.
        pool.shutdown(wait=False, cancel_futures=True)
    return results


def _fleet_captured_at(island_key: str) -> str:
    envelope = cache.get(fleet_cache_key(island_key)) or {}
    return str(envelope.get('fetched_at', ''))


def live_for_trips(island, trip_ids: list[int]) -> list[dict]:
    """One row per requested trip, in request order. Raises `TrackingDisabled`
    and `AzoresbusTrackingError` for the view to map; never raises for a trip
    that merely has no bus."""
    if not tracking_enabled(island):
        raise TrackingDisabled('tracking_disabled')

    journey_by_trip: dict[int, str] = dict(
        ExternalJourney.objects
        .filter(island=island, dataset=DATASET_AZORESBUS, trip_id__in=trip_ids)
        .values_list('trip_id', 'external_id')
    )

    fleet = get_fleet(island)  # refreshes the fleet and keeps the sweep alive
    fleet_by_id = {str(v.get('id')): v for v in fleet if v.get('id')}
    matches = match_vehicles(route_index(island), fleet_by_id.keys(), journey_by_trip.values())
    details = _read_details(island.key, sorted(set(matches.values())))
    identity = safe_stop_identity_map(island)
    captured_at = _fleet_captured_at(island.key)

    rows: list[dict] = []
    for trip_id in trip_ids:
        journey_id = journey_by_trip.get(trip_id)
        if journey_id is None:
            rows.append({'tripId': trip_id, 'state': STATE_UNSUPPORTED, 'vehicle': None})
            continue
        vehicle_id = matches.get(journey_id)
        if vehicle_id is None:
            rows.append({'tripId': trip_id, 'state': STATE_NOT_FOUND, 'vehicle': None})
            continue
        raw = details.get(vehicle_id)
        if raw is None:
            vehicle = serialize_live_vehicle(
                fleet_by_id[vehicle_id], {}, captured_at, [], stale=True,
            )
        elif str((raw.get('journey') or {}).get('id', '')) != journey_id:
            # The index lagged; the bus has moved on to another journey.
            rows.append({'tripId': trip_id, 'state': STATE_NOT_FOUND, 'vehicle': None})
            continue
        else:
            vehicle = serialize_live_vehicle(
                fleet_by_id[vehicle_id], raw, captured_at,
                upcoming_stops_from_detail(raw, identity), stale=False,
            )
        rows.append({'tripId': trip_id, 'state': STATE_LIVE, 'vehicle': vehicle})
    return rows
