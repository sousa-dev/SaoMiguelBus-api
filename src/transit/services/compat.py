"""Serialize new models into legacy API response shapes."""

from __future__ import annotations

from django.utils import timezone

from tenancy.models import Island
from tenancy.services import get_active_island
from transit.models import Calendar, Holiday, RouteInfo, Stop, StopTime, Trip
from transit.services.schedule_phase import resolve_dataset
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


def legacy_day_type_for_trip(trip: Trip) -> str:
    """The legacy WEEKDAY|SATURDAY|SUNDAY bucket this trip belongs in.

    AzoresBus trips carry a ServicePattern and NO Calendar, so dereferencing
    `trip.calendar` raised AttributeError. That mattered most here: this feeds
    `_trip_to_load_route`, so once `resolve_dataset` returned azoresbus the v1
    offline bundle would 500 for every already-installed build -- on the one day
    it must not.

    The projection is deliberately lossy and documented as such (02 section 7.3):
    a v1 client cannot see that line 112 runs on Tuesday and Thursday only. It
    gets the coarsest true bucket, and the v2 bundle carries the real calendar.
    Saturday and Sunday are checked first because a weekend-only service must not
    be advertised as a weekday one.
    """
    if trip.calendar_id:
        return _legacy_service_type(trip.calendar)

    service = trip.service if trip.service_id else None
    if service is None:
        return 'WEEKDAY'
    if any((service.monday, service.tuesday, service.wednesday,
            service.thursday, service.friday)):
        return 'WEEKDAY'
    if service.saturday:
        return 'SATURDAY'
    if service.sunday:
        return 'SUNDAY'
    return 'WEEKDAY'


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
        'weekday': legacy_day_type_for_trip(trip),
        'information': information,
        'likes': trip.likes,
        'dislikes': trip.dislikes,
        'likes_percent': likes_percent,
        'dislikes_percent': dislikes_percent,
    }


def _serialize_active_infos(dataset: str | None = None) -> list[dict]:
    now = timezone.now()
    # Post-cutover, legacy disruption notices describe an operator that no
    # longer runs (02 section 3.8).
    if dataset is None:
        dataset = resolve_dataset(get_active_island())
    infos = RouteInfo.objects.filter(
        dataset=dataset, start__lte=now, end__gte=now,
    )
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

    # Single-dataset for good: this is the fallback target for ANY v3 error,
    # not just a 404, and old clients cannot filter rows (98 B3).
    dataset = resolve_dataset(island)
    trips = (
        Trip.objects.filter(source=Trip.SOURCE_OPERATOR, dataset=dataset)
        .select_related('line', 'calendar')
        .exclude(line__disabled=True)
    )
    for trip in trips:
        load_route = _trip_to_load_route(trip)
        all_stop_names.update(load_route['stops'])
        routes_payload.append(load_route)

    routes_payload[0]['stops'] = sorted(all_stop_names)
    return routes_payload
