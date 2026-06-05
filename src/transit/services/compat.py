"""Serialize new models into legacy API response shapes."""

from __future__ import annotations

from django.utils import timezone

from tenancy.models import Island
from transit.models import Calendar, Holiday, RouteInfo, Stop, StopTime, Trip
from transit.services.search import trip_vote_percents


def serialize_legacy_stops_v2(stops) -> list[dict]:
    """Match legacy GET /api/v2/stops duplicate-name dedupe behavior."""
    payload: list[dict] = []
    seen_short_names: set[str] = set()
    extras: list[dict] = []

    for stop in stops:
        payload.append(
            {
                'id': stop.id,
                'name': stop.name,
                'latitude': stop.latitude,
                'longitude': stop.longitude,
            }
        )
        short_name = stop.name.split(' - ')[0]
        if short_name not in seen_short_names:
            seen_short_names.add(short_name)
            extras.append(
                {
                    'id': stop.id,
                    'name': short_name,
                    'latitude': stop.latitude,
                    'longitude': stop.longitude,
                }
            )

    return payload + extras


def _legacy_service_type(calendar: Calendar) -> str:
    mapping = {
        Calendar.WEEKDAY: 'WEEKDAY',
        Calendar.SATURDAY: 'SATURDAY',
        Calendar.SUNDAY: 'SUNDAY',
    }
    return mapping.get(calendar.service_type, calendar.service_type)


def _trip_to_load_route(trip: Trip) -> dict:
    stop_times = list(
        StopTime.objects.filter(trip=trip).select_related('stop').order_by('sequence')
    )
    route_stops = [st.stop.name for st in stop_times]
    all_times = [st.departure_time.strftime('%H:%M').replace(':', 'h') for st in stop_times]
    information = trip.information if trip.information else {}
    likes_percent, dislikes_percent = trip_vote_percents(trip)
    return {
        'id': trip.id,
        'route': trip.line.code,
        'stops': route_stops,
        'times': all_times,
        'weekday': _legacy_service_type(trip.calendar),
        'information': information,
        'likes': trip.likes,
        'dislikes': trip.dislikes,
        'likes_percent': likes_percent,
        'dislikes_percent': dislikes_percent,
    }


def _serialize_active_infos() -> list[dict]:
    now = timezone.now()
    infos = RouteInfo.objects.filter(start__lte=now, end__gte=now)
    result = []
    for info in infos:
        text = info.text or {}
        result.append(
            {
                'id': info.id,
                'titlePT': text.get('pt', {}).get('title', ''),
                'messagePT': text.get('pt', {}).get('message', ''),
                'titleEN': text.get('en', {}).get('title', ''),
                'messageEN': text.get('en', {}).get('message', ''),
                'titleES': text.get('es', {}).get('title', ''),
                'messageES': text.get('es', {}).get('message', ''),
                'titleFR': text.get('fr', {}).get('title', ''),
                'messageFR': text.get('fr', {}).get('message', ''),
                'titleDE': text.get('de', {}).get('title', ''),
                'messageDE': text.get('de', {}).get('message', ''),
                'start': info.start.isoformat() if info.start else None,
                'end': info.end.isoformat() if info.end else None,
                'source': info.source,
                'company': info.company,
            }
        )
    return result


def serialize_webapp_load_v2(island: Island) -> list[dict]:
    """Match legacy GET /api/v2/webapp/load list payload."""
    holidays = [
        {'id': h.id, 'date': h.date.isoformat(), 'name': h.name}
        for h in Holiday.objects.all().order_by('date')
    ]
    flags = island.feature_flags or {}
    header = {
        'version': flags.get('version', '5.0.0'),
        'maps': flags.get('maps', False),
        'holidays': holidays,
        'infos': _serialize_active_infos(),
        'stops': [],
    }

    all_stop_names: set[str] = set()
    routes_payload: list[dict] = [header]

    trips = (
        Trip.objects.filter(source=Trip.SOURCE_OPERATOR)
        .select_related('line', 'calendar')
        .exclude(line__disabled=True)
    )
    for trip in trips:
        load_route = _trip_to_load_route(trip)
        all_stop_names.update(load_route['stops'])
        routes_payload.append(load_route)

    routes_payload[0]['stops'] = sorted(all_stop_names)
    return routes_payload
