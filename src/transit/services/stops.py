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
            'headsign': stop_time.trip.headsign or '',
        }
        if stop_time.external_stop is not None:
            row['code'] = stop_time.external_stop.code
        departures.append(row)

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
