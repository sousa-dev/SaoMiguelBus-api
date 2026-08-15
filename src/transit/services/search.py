"""Route search ported from legacy get_trip_v1_logic / get_trip_v2."""

from __future__ import annotations

from datetime import datetime, time

from azoresbus.services_stops import build_area_index
from tenancy.services import get_active_island
from transit.models import (
    DATASET_AZORESBUS,
    Calendar,
    Holiday,
    ServiceException,
    ServicePattern,
    Stop,
    Trip,
)
from transit.services.legacy_import import clean_string
from transit.services.matcher import select_pair
from transit.services.schedule_phase import resolve_dataset


def get_type_of_day(day: datetime, is_holiday: bool) -> str:
    if is_holiday:
        return Calendar.SUNDAY
    weekday = day.weekday()
    if weekday == 5:
        return Calendar.SATURDAY
    if weekday == 6:
        return Calendar.SUNDAY
    return Calendar.WEEKDAY


DAY_TYPE_TO_WEEKDAYS = {
    Calendar.WEEKDAY: (0, 1, 2, 3, 4),
    Calendar.SATURDAY: (5,),
    Calendar.SUNDAY: (6,),
}


def eligible_trips(queryset, *, day_type: str | None, on_date=None):
    """Filter trips to those whose ServicePattern actually runs.

    Two request shapes, because every shipped client sends the second:

      on_date   an ISO date -> exact per-weekday and seasonal resolution.
      day_type  weekday|saturday|sunday, with NO date. `weekday` requires all
                five of Mon-Fri, so a partial-week journey (112 is Tue/Thu only)
                is omitted rather than offered on a day it does not run.
                Under-inclusive is the right failure for transit: showing a bus
                that is not coming strands someone at a stop.
    """
    from django.db.models import Q

    if on_date is not None:
        weekday_field = ServicePattern.WEEKDAY_FIELDS[on_date.weekday()]
        return (
            queryset.filter(**{f'service__{weekday_field}': True})
            .filter(
                Q(service__start_date__isnull=True)
                | Q(service__start_date__lte=on_date)
            )
            .filter(
                Q(service__end_date__isnull=True)
                | Q(service__end_date__gte=on_date)
            )
            .exclude(
                service__exceptions__date=on_date,
                service__exceptions__exception_type=ServiceException.REMOVED,
            )
        )

    for weekday in DAY_TYPE_TO_WEEKDAYS.get(day_type, ()):
        queryset = queryset.filter(
            **{f'service__{ServicePattern.WEEKDAY_FIELDS[weekday]}': True}
        )
    return queryset


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


def trip_vote_percents(trip: Trip) -> tuple[int, int]:
    """Return (likes_percent, dislikes_percent) for a trip."""
    return _trip_likes_percent(trip), _trip_dislikes_percent(trip)


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


def _resolve_stop_ids(
    dataset: str, cleaned: str, area_index: dict[str, set[int]] | None,
) -> set[int]:
    """By id, not fuzzy substring, resolving to a SET of one or more stops.

    The string matcher produced containment mis-hits: a search for LAGOA
    matched a trip that only serves LAGOA DO FOGO (02 §3.4).

    Precedence, in order:
      1. An exact `cleaned_name` match always wins. This is what keeps a
         village-shaped exact stop (e.g. a bare "Aflitos") behaving exactly as
         it did before areas existed -- `area_index` never even contains a key
         that collides with a real stop's exact name (`build_area_index`).
      2. A village area match (AzoresBus only, via `area_index`) -- every stop
         sharing that village's name prefix.
      3. The existing single-stop prefix fallback, unchanged.

    Never returns `None`; an unresolved query is an empty set.
    """
    exact = Stop.objects.filter(dataset=dataset, cleaned_name=cleaned).first()
    if exact:
        return {exact.id}

    if area_index is not None and cleaned in area_index:
        return set(area_index[cleaned])

    fallback = Stop.objects.filter(
        dataset=dataset, cleaned_name__startswith=cleaned,
    ).order_by('cleaned_name').first()
    return {fallback.id} if fallback else set()


def _type_of_day_for(trip: Trip, service_type: str | None) -> str:
    """AzoresBus trips have no Calendar, so derive rather than dereference."""
    if trip.calendar_id:
        return trip.calendar.service_type
    return service_type or Calendar.WEEKDAY


def _attach_boarding(row: dict, board, alight) -> None:
    """02 §7.1b: additive and optional.

    `sequence` is load-bearing, not decorative -- the app must slice on these
    indices instead of re-matching names, or it discards the pair the server
    just chose (98 B7). Legacy rows have no ExternalStop and omit the keys
    entirely rather than emitting nulls.
    """
    for key, stop_time in (('boarding', board), ('alighting', alight)):
        external = stop_time.external_stop
        if external is None:
            continue
        row[key] = {
            'code': external.code,
            'lat': external.latitude,
            'lon': external.longitude,
            'sequence': stop_time.sequence,
            'dayOffset': stop_time.day_offset,
        }


def search_routes(
    *,
    origin: str,
    destination: str,
    day: str,
    start_time: str,
    full: bool = False,
    prefix: bool = False,
    dataset: str | None = None,
) -> list[dict] | None:
    origin = _normalize_origin(origin)
    if not origin or not destination:
        return None

    origin_cleaned = clean_string(origin)
    destination_cleaned = clean_string(destination)

    service_type = day.upper()
    on_date = None
    if day and '-' in day:
        try:
            parsed = datetime.strptime(day, '%Y-%m-%d')
            on_date = parsed.date()
            is_holiday = Holiday.objects.filter(date=on_date).exists()
            service_type = get_type_of_day(parsed, is_holiday)
            if is_holiday:
                # Upstream resolves a holiday to its Sunday set, so eligibility
                # is evaluated as a Sunday rather than by the calendar weekday.
                on_date = None
        except ValueError:
            service_type = day.upper()

    start_hour, start_minute = _parse_time_parts(start_time.replace('h', ':'))

    if dataset is None:
        dataset = resolve_dataset(get_active_island(), on_date=on_date)

    # AzoresBus only (explicit gate, not just incidental data shape) -- legacy
    # names never carry the "VILLAGE (LANDMARK)" convention this groups on, and
    # this way legacy search pays zero extra cost for a lookup it never uses.
    area_index = (
        build_area_index(Stop.objects.filter(dataset=dataset).only('id', 'name'))
        if dataset == DATASET_AZORESBUS else None
    )

    origin_ids = _resolve_stop_ids(dataset, origin_cleaned, area_index)
    destination_ids = _resolve_stop_ids(dataset, destination_cleaned, area_index)
    if not origin_ids or not destination_ids:
        return []

    trips = eligible_trips(
        Trip.objects.filter(
            source=Trip.SOURCE_OPERATOR, line__disabled=False, dataset=dataset,
        ),
        day_type=service_type,
        on_date=on_date,
    ).select_related('line', 'calendar', 'service').prefetch_related(
        'stop_times__stop', 'stop_times__external_stop',
    )

    earliest = time(start_hour, start_minute) if (start_hour or start_minute) else None

    return_routes: list[dict] = []
    for trip in trips:
        pair = select_pair(
            trip, origin_ids, destination_ids, earliest=earliest,
        )
        if pair is None:
            continue
        board, alight = pair

        stop_times = list(trip.stop_times.all())
        if not stop_times:
            continue
        stop_times.sort(key=lambda st: st.sequence)

        likes_percent = _trip_likes_percent(trip)
        route_code = trip.line.code
        if prefix and likes_percent < 60:
            route_code = f'C{route_code}'

        row = {
            'id': trip.id,
            'route': route_code,
            'origin': origin,
            'destination': destination,
            'start': board.departure_time.strftime('%Hh%M'),
            'end': alight.departure_time.strftime('%Hh%M'),
            'stops': build_legacy_stops_string(trip),
            'type_of_day': _type_of_day_for(trip, service_type),
            'information': trip.information if trip.information else {},
            'likes_percent': likes_percent,
            'dislikes_percent': _trip_dislikes_percent(trip),
        }
        _attach_boarding(row, board, alight)
        return_routes.append(row)

    if not full:
        pass  # legacy TODO: trim stops outside scope

    return return_routes
