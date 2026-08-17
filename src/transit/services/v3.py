"""Canonical v3 transit serializers."""

from __future__ import annotations

import ast
import re

from transit.models import Line, Stop, StopTime, Trip
from transit.services.compat import serialize_legacy_stops_v2
from tenancy.services import get_active_island
from transit.services.schedule_phase import resolve_dataset
from transit.services.search import search_routes, trip_vote_percents


def serialize_stops_v3(stops) -> list[dict]:
    """Stops list for mobile — includes short-name aliases like legacy v2."""
    return serialize_legacy_stops_v2(stops)


def _parse_stops_string(stops_str: str) -> list[dict]:
    """Parse the legacy stops dict string into ordered {name, time} entries.

    Walks the AST rather than calling ``literal_eval``, and that distinction is
    load-bearing. The string carries every stop in sequence order, but building a
    dict from it COLLAPSES repeated stop names: the first occurrence's position
    survives holding the last occurrence's time. On line 301 journey 488 that
    turned 59 stops into 45, so ``alighting.sequence`` 59 indexed past the end of
    the array and the client could not slice on the pair the server had chosen
    (98 B7, 03 section 5c). Loop routes are exactly the ones that repeat names,
    so this hit precisely the trips sequence matching exists to fix.

    Walking the AST keeps duplicates, keeps order, and still handles quoting
    correctly -- which the regex fallback below does not.
    """
    if not stops_str:
        return []
    try:
        node = ast.parse(stops_str, mode='eval').body
        if isinstance(node, ast.Dict):
            return [
                {'name': key.value, 'time': value.value}
                for key, value in zip(node.keys, node.values)
                if isinstance(key, ast.Constant) and isinstance(value, ast.Constant)
            ]
    except (SyntaxError, ValueError):
        pass
    pattern = re.findall(r"'([^']+)':\s*'([^']+)'", stops_str)
    return [{'name': name, 'time': time} for name, time in pattern]


def serialize_search_results(routes: list[dict]) -> list[dict]:
    results = []
    for route in routes:
        results.append(
            {
                'id': route['id'],
                'route': route['route'],
                'origin': route['origin'],
                'destination': route['destination'],
                'start': route['start'],
                'end': route['end'],
                'typeOfDay': route.get('type_of_day'),
                'likesPercent': route.get('likes_percent', 0),
                'dislikesPercent': route.get('dislikes_percent', 0),
                'information': route.get('information') or {},
                'stops': _parse_stops_string(route.get('stops', '')),
            }
        )
        # 02 §7.1b: additive and optional. `sequence` is load-bearing -- the app
        # must slice on these indices instead of re-matching names, or it
        # discards the pair the server just chose (98 B7). Legacy results have
        # no ExternalStop and omit the keys rather than emitting nulls.
        for key in ('boarding', 'alighting'):
            if route.get(key):
                results[-1][key] = route[key]
    return results


def serialize_trip_detail(trip: Trip) -> dict:
    stop_times = list(
        StopTime.objects.filter(trip=trip).select_related('stop').order_by('sequence')
    )
    likes_percent, dislikes_percent = trip_vote_percents(trip)
    return {
        'id': trip.id,
        'route': trip.line.code,
        # AzoresBus trips are date-resolved through `service` and carry no
        # Calendar -- the importer writes calendar=None -- so dereferencing it
        # raised AttributeError and 500'd every trip detail on the new network.
        # Search already derives this (search.py:_type_of_day_for); detail did not.
        'typeOfDay': trip.calendar.service_type if trip.calendar_id else None,
        'likes': trip.likes,
        'dislikes': trip.dislikes,
        'likesPercent': likes_percent,
        'dislikesPercent': dislikes_percent,
        'information': trip.information if trip.information else {},
        'stops': [
            {
                'name': st.stop.name,
                'time': st.departure_time.strftime('%Hh%M'),
                'sequence': st.sequence,
            }
            for st in stop_times
        ],
    }


def get_trip_v3(trip_id: int, *, dataset: str | None = None) -> dict | None:
    dataset = dataset or resolve_dataset(get_active_island())
    try:
        trip = (
            Trip.objects.filter(dataset=dataset)
            .select_related('line', 'calendar')
            .get(id=trip_id)
        )
    except Trip.DoesNotExist:
        return None
    return serialize_trip_detail(trip)


def get_line_v3(line_code: str, *, dataset: str | None = None) -> dict | None:
    # Without the dataset filter this raises MultipleObjectsReturned the moment
    # line 101 exists in both networks -- and legacy already has 101 (98 B4).
    dataset = dataset or resolve_dataset(get_active_island())
    try:
        line = (
            Line.objects.filter(dataset=dataset)
            .select_related('operator')
            .get(code=line_code)
        )
    except Line.DoesNotExist:
        return None

    # Already dataset-scoped: `line` was resolved under the active dataset.
    trips = (
        Trip.objects.filter(line=line, line__disabled=False)
        .select_related('calendar')
        .order_by('calendar__service_type', 'id')[:50]
    )
    return {
        'code': line.code,
        'displayName': line.display_name,
        'operator': line.operator.name,
        'disabled': line.disabled,
        'trips': [
            {
                'id': trip.id,
                # Null on AzoresBus trips, which are date-resolved through
                # `service` and carry no Calendar (see serialize_trip_detail).
                'typeOfDay': trip.calendar.service_type if trip.calendar_id else None,
                'headsign': trip.headsign,
                'likes': trip.likes,
                'dislikes': trip.dislikes,
            }
            for trip in trips
        ],
    }


def _leg_stop_ref(stop_time) -> dict:
    """One end of a ride. `sequence` is load-bearing (02 §7.1b) -- the client
    slices the stop list on it instead of re-matching by name."""
    return {
        'name': stop_time.stop.name,
        'time': stop_time.departure_time.strftime('%Hh%M'),
        'sequence': stop_time.sequence,
        'dayOffset': stop_time.day_offset,
    }


def _leg_pole_ref(stop_time) -> dict | None:
    """The physical pole, when upstream told us which one.

    Legacy rows have no `ExternalStop`; callers omit the key entirely rather
    than emitting nulls, matching `serialize_search_results`.
    """
    external = stop_time.external_stop
    if external is None:
        return None
    return {
        'code': external.code,
        'lat': external.latitude,
        'lon': external.longitude,
        'sequence': stop_time.sequence,
        'dayOffset': stop_time.day_offset,
    }


def _serialize_ride_leg(leg, *, prefix: bool) -> dict:
    from transit.services.journeys import leg_vote_percents

    likes_percent, dislikes_percent = leg_vote_percents(leg)
    route_code = leg.trip.line.code
    if prefix and likes_percent < 60:
        route_code = f'C{route_code}'

    stop_times = sorted(leg.trip.stop_times.all(), key=lambda st: st.sequence)
    segment = [
        {
            'name': st.stop.name,
            'time': st.departure_time.strftime('%Hh%M'),
            'sequence': st.sequence,
        }
        for st in stop_times
        if leg.board.sequence <= st.sequence <= leg.alight.sequence
    ]

    row = {
        'kind': 'ride',
        'tripId': leg.trip.id,
        'route': route_code,
        'likesPercent': likes_percent,
        'dislikesPercent': dislikes_percent,
        'information': leg.trip.information if leg.trip.information else {},
        'board': _leg_stop_ref(leg.board),
        'alight': _leg_stop_ref(leg.alight),
        'stops': segment,
    }
    for key, stop_time in (('boarding', leg.board), ('alighting', leg.alight)):
        pole = _leg_pole_ref(stop_time)
        if pole is not None:
            row[key] = pole
    return row


def serialize_journeys(journeys, *, service_type: str | None, prefix: bool = True) -> list[dict]:
    """Journeys as alternating ride / transfer legs.

    The transfer leg is a real entry rather than a property of the ride after it,
    because that is what the rider actually does -- get off, wait, walk -- and it
    lets the app render the itinerary as a flat step list.
    """
    from transit.services.journeys import journey_service_day

    results = []
    for journey in journeys:
        legs: list[dict] = []
        for index, leg in enumerate(journey.legs):
            if index > 0:
                previous = journey.legs[index - 1]
                wait = journey.waits[index - 1]
                walk = transfer_minutes_between(previous.alight, leg.board)
                legs.append(
                    {
                        'kind': 'transfer',
                        'at': leg.board.stop.name,
                        'from': previous.alight.stop.name,
                        'waitMinutes': wait,
                        'walkMinutes': walk,
                        'fromRoute': previous.trip.line.code,
                        'toRoute': leg.trip.line.code,
                    }
                )
            legs.append(_serialize_ride_leg(leg, prefix=prefix))

        first, last = journey.legs[0], journey.legs[-1]
        results.append(
            {
                'id': ':'.join(str(leg.trip.id) for leg in journey.legs),
                'transfers': journey.transfers,
                'start': first.board.departure_time.strftime('%Hh%M'),
                'end': last.alight.departure_time.strftime('%Hh%M'),
                'durationMinutes': journey.arrival - journey.departure,
                'waitMinutes': sum(journey.waits),
                'dayOffset': last.alight.day_offset,
                'typeOfDay': journey_service_day(journey, service_type),
                'legs': legs,
            }
        )
    return results


def transfer_minutes_between(alight, board) -> int:
    """Walking minutes between two stops, 0 when the change is at one stop."""
    from transit.services.transfer_points import walk_minutes
    from azoresbus.services_stops import haversine_m

    if alight.stop_id == board.stop_id:
        return 0
    return walk_minutes(
        haversine_m(
            alight.stop.latitude, alight.stop.longitude,
            board.stop.latitude, board.stop.longitude,
        )
    )


def search_journeys_v3(
    *,
    origin: str,
    destination: str,
    day: str,
    start_time: str,
    dataset: str | None = None,
    max_transfers: int | None = None,
) -> dict | None:
    """Direct rides AND one-transfer itineraries, in one payload.

    Direct journeys are included so the app makes a single call and renders one
    card type. `/transit/search` stays exactly as it is for shipped builds, which
    have no concept of a leg and would render a two-bus journey as one bus.

    `max_transfers=0` answers with a single bus only.

    When that returns NOTHING, and only then, the search is retried with
    transfers allowed so the answer can carry `transfersAvailable`. That number
    is what lets the app say "no direct bus, but 4 journeys with one change" and
    offer them, instead of guessing that a change might help and finding it does
    not. The extra scan costs one more pass over the same trips, and it happens
    exactly when the rider is otherwise being told "nothing" -- never on a
    request that already has an answer.
    """
    from transit.services.journeys import (
        MAX_SUPPORTED_TRANSFERS,
        resolve_service_day,
        search_journeys,
    )

    if max_transfers is None:
        max_transfers = MAX_SUPPORTED_TRANSFERS
    max_transfers = max(0, min(max_transfers, MAX_SUPPORTED_TRANSFERS))

    journeys = search_journeys(
        origin=origin,
        destination=destination,
        day=day,
        start_time=start_time,
        dataset=dataset,
        max_transfers=max_transfers,
    )
    if journeys is None:
        return None

    service_type, _ = resolve_service_day(day)
    payload = {
        'maxTransfers': max_transfers,
        'journeys': serialize_journeys(
            journeys, service_type=service_type, prefix=True,
        ),
    }

    if max_transfers == 0 and not journeys:
        with_transfers = search_journeys(
            origin=origin,
            destination=destination,
            day=day,
            start_time=start_time,
            dataset=dataset,
            max_transfers=MAX_SUPPORTED_TRANSFERS,
        ) or []
        payload['transfersAvailable'] = sum(
            1 for journey in with_transfers if journey.transfers > 0
        )

    return payload


def search_transit_v3(
    *,
    origin: str,
    destination: str,
    day: str,
    start_time: str,
    dataset: str | None = None,
) -> list[dict] | None:
    """`dataset` is the preview toggle and admin/debug only (02 §7.1).

    The app must never populate it from a cached bootstrap value, and must never
    send `dataset=legacy` on a public URL (98 §4 gap "Stale bootstrap").
    """
    routes = search_routes(
        origin=origin,
        destination=destination,
        day=day,
        start_time=start_time,
        full=False,
        prefix=True,
        dataset=dataset,
    )
    if routes is None:
        return None
    routes.sort(key=lambda item: item['start'])
    return serialize_search_results(routes)
