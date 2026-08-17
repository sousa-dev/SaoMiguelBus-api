"""One stop, answered the way someone standing near it would ask.

Three questions, in the order a rider actually has them:

  where exactly is it?   The POLES, not the collapsed `Stop` row. A `Stop` is
                         the centroid of every pole sharing a name
                         (`azoresbus/services_stops.py:97`), so on a two-sided
                         road it lands in the middle of the carriageway — the
                         one place you cannot stand. Each pole carries the code
                         printed on the sign, which is the best disambiguation
                         there is.
  what stops here?       The lines, deduplicated, in the order a human reads.
  when is the next one?  Departures, resolved through the SAME service rules as
                         search, so a stop page can never promise a bus that
                         `/journeys` would refuse to plan.
"""

from __future__ import annotations

from transit.models import StopTime, Trip
from transit.services.search import eligible_trips, parse_time_parts

# Enough to answer "is there one soon?" without turning a stop page into a
# timetable. The full timetable is the line's job.
DEFAULT_DEPARTURE_LIMIT = 12


def _minutes(stop_time) -> int:
    return (
        stop_time.day_offset * 1440
        + stop_time.departure_time.hour * 60
        + stop_time.departure_time.minute
    )


def stop_poles(stop) -> list[dict]:
    """Every physical pole collapsed into this stop, nearest-code order.

    Empty on the legacy dataset, which has no `ExternalStop` rows at all.
    """
    externals = getattr(stop, 'external_stops', None)
    if externals is None:
        return []
    return [
        {
            'code': external.code,
            'name': external.name,
            'lat': external.latitude,
            'lon': external.longitude,
        }
        for external in sorted(externals.all(), key=lambda e: e.code)
    ]


def serialize_stop_detail(stop, *, day: str, start_time: str,
                          limit: int = DEFAULT_DEPARTURE_LIMIT) -> dict:
    """The stop, its poles, the lines that serve it and what leaves next."""
    from transit.services.journeys import resolve_service_day

    service_type, on_date = resolve_service_day(day)
    start_hour, start_minute = parse_time_parts(start_time.replace('h', ':'))
    earliest = start_hour * 60 + start_minute

    trips = eligible_trips(
        Trip.objects.filter(
            dataset=stop.dataset,
            source=Trip.SOURCE_OPERATOR,
            line__disabled=False,
        ),
        day_type=service_type,
        on_date=on_date,
    )

    stop_times = (
        StopTime.objects.filter(stop=stop, trip__in=trips)
        .select_related('trip__line', 'external_stop')
        .order_by('day_offset', 'departure_time')
    )

    departures = []
    lines: dict[str, str] = {}
    candidates = []

    for stop_time in stop_times:
        code = stop_time.trip.line.code
        lines.setdefault(code, code)

        if _minutes(stop_time) < earliest:
            continue
        if len(departures) >= limit:
            continue

        row = {
            'tripId': stop_time.trip_id,
            'route': code,
            'time': stop_time.departure_time.strftime('%Hh%M'),
            'dayOffset': stop_time.day_offset,
            'sequence': stop_time.sequence,
            # Where this bus is going, so "110 at 09h15" means something. The
            # importer fills `headsign` from the upstream journey name.
            # Kept because it is what upstream sent, but `destination` below is
            # what a rider should be shown.
            'headsign': stop_time.trip.headsign or '',
        }
        if stop_time.external_stop is not None:
            row['code'] = stop_time.external_stop.code
        departures.append(row)
        candidates.append(stop_time.trip_id)

    # "Where is this bus going?" is the whole point of a departure row, and
    # upstream's journey `name` does NOT answer it -- on the live API it holds a
    # time range ("08:00 » 08:50"), so `headsign` renders as noise. The honest
    # answer is the trip's LAST stop, resolved in one query for the whole page
    # rather than one per row.
    for trip_id, name in _terminal_stop_names(candidates).items():
        for row in departures:
            if row['tripId'] == trip_id:
                row['destination'] = name

    return {
        'id': stop.id,
        'name': stop.name,
        'lat': stop.latitude,
        'lon': stop.longitude,
        'dataset': stop.dataset,
        'poles': stop_poles(stop),
        # Sorted, because a stop page that reorders its own line list between
        # two visits looks broken.
        'lines': sorted(lines),
        'departures': departures,
    }


def _terminal_stop_names(trip_ids: list[int]) -> dict[int, str]:
    """Final stop name per trip, in one query.

    The last stop by `sequence`, never by time: a night trip wraps past midnight
    and ordering on the bare time field would pick the wrong end (98 B2).
    """
    if not trip_ids:
        return {}

    rows = (
        StopTime.objects.filter(trip_id__in=set(trip_ids))
        .select_related('stop')
        .order_by('trip_id', 'sequence')
        .values_list('trip_id', 'stop__name')
    )
    terminal: dict[int, str] = {}
    for trip_id, name in rows:
        terminal[trip_id] = name        # last write wins == highest sequence
    return terminal
