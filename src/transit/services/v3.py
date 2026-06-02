"""Canonical v3 transit serializers."""

from __future__ import annotations

import ast
import re

from transit.models import Line, Stop, StopTime, Trip
from transit.services.compat import serialize_legacy_stops_v2
from transit.services.search import search_routes


def serialize_stops_v3(stops) -> list[dict]:
    """Stops list for mobile — includes short-name aliases like legacy v2."""
    return serialize_legacy_stops_v2(stops)


def _parse_stops_string(stops_str: str) -> list[dict]:
    """Parse legacy stops dict string into ordered {name, time} entries."""
    if not stops_str:
        return []
    try:
        parsed = ast.literal_eval(stops_str)
        if isinstance(parsed, dict):
            return [{'name': name, 'time': time} for name, time in parsed.items()]
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
    return results


def serialize_trip_detail(trip: Trip) -> dict:
    stop_times = list(
        StopTime.objects.filter(trip=trip).select_related('stop').order_by('sequence')
    )
    return {
        'id': trip.id,
        'route': trip.line.code,
        'typeOfDay': trip.calendar.service_type,
        'likes': trip.likes,
        'dislikes': trip.dislikes,
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


def get_trip_v3(trip_id: int) -> dict | None:
    try:
        trip = Trip.objects.select_related('line', 'calendar').get(id=trip_id)
    except Trip.DoesNotExist:
        return None
    return serialize_trip_detail(trip)


def get_line_v3(line_code: str) -> dict | None:
    try:
        line = Line.objects.select_related('operator').get(code=line_code)
    except Line.DoesNotExist:
        return None

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
                'typeOfDay': trip.calendar.service_type,
                'headsign': trip.headsign,
                'likes': trip.likes,
                'dislikes': trip.dislikes,
            }
            for trip in trips
        ],
    }


def search_transit_v3(
    *,
    origin: str,
    destination: str,
    day: str,
    start_time: str,
) -> list[dict] | None:
    routes = search_routes(
        origin=origin,
        destination=destination,
        day=day,
        start_time=start_time,
        full=False,
        prefix=True,
    )
    if routes is None:
        return None
    routes.sort(key=lambda item: item['start'])
    return serialize_search_results(routes)
