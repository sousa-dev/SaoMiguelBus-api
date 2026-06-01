"""Route search ported from legacy get_trip_v1_logic / get_trip_v2."""

from __future__ import annotations

from datetime import datetime

from transit.models import Calendar, Holiday, Trip
from transit.services.legacy_import import clean_string


def get_type_of_day(day: datetime, is_holiday: bool) -> str:
    if is_holiday:
        return Calendar.SUNDAY
    weekday = day.weekday()
    if weekday == 5:
        return Calendar.SATURDAY
    if weekday == 6:
        return Calendar.SUNDAY
    return Calendar.WEEKDAY


def _normalize_origin(origin: str) -> str:
    if origin in ['Povoacão', 'Lomba do Loucão', 'Ponta Garca']:
        return origin.replace('c', 'ç')
    return origin


def _parse_time_parts(raw: str) -> tuple[int, int]:
    if not raw:
        return 0, 0
    normalized = raw.replace('h', ':')
    hour, minute = map(int, normalized.split(':'))
    return hour, minute


def _trip_likes_percent(trip: Trip) -> int:
    total = trip.likes + trip.dislikes
    return int(trip.likes / total * 100) if total > 0 else 0


def _trip_dislikes_percent(trip: Trip) -> int:
    total = trip.likes + trip.dislikes
    return int(trip.dislikes / total * 100) if total > 0 else 0


def build_legacy_stops_string(trip: Trip) -> str:
    stop_times = trip.stop_times.select_related('stop').order_by('sequence')
    parts = []
    for st in stop_times:
        time_str = st.departure_time.strftime('%Hh%M')
        parts.append(f"'{st.stop.name}': '{time_str}'")
    return '{' + ', '.join(parts) + '}'


def _trip_cleaned_stops_blob(trip: Trip) -> str:
    stop_times = trip.stop_times.select_related('stop').order_by('sequence')
    return clean_string(build_legacy_stops_string(trip))


def search_routes(
    *,
    origin: str,
    destination: str,
    day: str,
    start_time: str,
    full: bool = False,
    prefix: bool = False,
) -> list[dict] | None:
    origin = _normalize_origin(origin)
    if not origin or not destination:
        return None

    origin_cleaned = clean_string(origin)
    destination_cleaned = clean_string(destination)

    service_type = day.upper()
    if day and '-' in day:
        try:
            day_date = datetime.strptime(day, '%Y-%m-%d')
            is_holiday = Holiday.objects.filter(date=day_date.date()).exists()
            service_type = get_type_of_day(day_date, is_holiday)
        except ValueError:
            service_type = day.upper()

    start_hour, start_minute = _parse_time_parts(start_time.replace('h', ':'))

    trips = (
        Trip.objects.filter(source=Trip.SOURCE_OPERATOR, line__disabled=False)
        .filter(calendar__service_type=service_type)
        .select_related('line', 'calendar')
        .prefetch_related('stop_times__stop')
    )

    return_routes: list[dict] = []
    for trip in trips:
        blob = _trip_cleaned_stops_blob(trip)
        if origin_cleaned not in blob or destination_cleaned not in blob:
            continue

        stops_str = build_legacy_stops_string(trip)
        if stops_str.find(origin) > stops_str.find(destination):
            continue

        stop_times = list(trip.stop_times.select_related('stop').order_by('sequence'))
        if not stop_times:
            continue

        first_time = stop_times[0].departure_time.strftime('%Hh%M')
        route_start_hour, route_start_minute = _parse_time_parts(first_time)
        if route_start_hour < start_hour or (
            route_start_hour == start_hour and route_start_minute < start_minute
        ):
            continue

        last_time = stop_times[-1].departure_time.strftime('%Hh%M')
        likes_percent = _trip_likes_percent(trip)
        route_code = trip.line.code
        if prefix and likes_percent < 60:
            route_code = f'C{route_code}'

        return_routes.append(
            {
                'id': trip.id,
                'route': route_code,
                'origin': origin,
                'destination': destination,
                'start': first_time,
                'end': last_time,
                'stops': stops_str,
                'type_of_day': trip.calendar.service_type,
                'information': trip.information if trip.information else {},
                'likes_percent': likes_percent,
                'dislikes_percent': _trip_dislikes_percent(trip),
            }
        )

    if not full:
        pass  # legacy TODO: trim stops outside scope

    return return_routes
