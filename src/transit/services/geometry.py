"""The path a rider actually travels, drawn from geometry we already store.

`ExternalJourney.shape` has held a Google-encoded polyline per AzoresBus trip
since the schedule importer was written (`azoresbus/services_import.py:285`) and
nothing has ever read it. Decoded, a representative one is 916 points over 36 km
with a median vertex gap of 24 m -- real road-following geometry, already keyed
to `transit.Trip`.

TWO things this module exists to get right.

**Trimming.** A journey uses part of a trip. Drawing the whole trip's shape would
show the bus travelling to places the rider never rides -- on a route that loops
back through Ponta Delgada that is not a cosmetic problem, it is a wrong map.
`trim_shape` cuts the polyline down to the leg.

**Poles, not centroids.** `transit.Stop` is a centroid of every pole sharing a
name (`azoresbus/services_stops.py:97`), which is the right thing for a picker
and the wrong thing for a map: it can sit in the middle of a road, on neither
side. `StopTime.external_stop` knows the exact pole the trip serves, and that is
what a rider walking to a stop needs. We fall back to the centroid only when
there is no pole, which on the legacy dataset is always.

Legacy carries neither shape nor pole, so every function here returns empty for
it. That is the gate: the client offers a map when geometry arrives, and legacy
never sends any.
"""

from __future__ import annotations

from shared.geo import (
    decode_polyline,
    encode_polyline,
    haversine_km,
    is_plausible_route_coordinates,
)

# How far a stop may sit from the polyline before we stop believing they describe
# the same journey. Generous on purpose: the shape follows the road while the
# stop sits at the kerb, and on a dual carriageway that is a real separation.
# Beyond this the two are not the same route and a trimmed path would be a guess.
MAX_STOP_TO_SHAPE_KM = 0.5


def _nearest_index(points: list[tuple[float, float]], lat: float, lon: float) -> tuple[int, float]:
    """Index of the closest vertex, and how far away it is in km."""
    best_index = 0
    best_distance = float('inf')
    for index, (point_lat, point_lon) in enumerate(points):
        distance = haversine_km(lat, lon, point_lat, point_lon)
        if distance < best_distance:
            best_index = index
            best_distance = distance
    return best_index, best_distance


def stop_time_position(stop_time) -> tuple[float, float] | None:
    """Where this stop physically is: the pole if we know it, else the centroid."""
    external = getattr(stop_time, 'external_stop', None)
    if external is not None:
        return (external.latitude, external.longitude)
    stop = getattr(stop_time, 'stop', None)
    if stop is None:
        return None
    return (stop.latitude, stop.longitude)


def trip_shape(trip) -> str:
    """The stored encoded polyline for a trip, or '' when it has none.

    One `ExternalJourney` per trip, but the FK is a reverse relation and a legacy
    trip has none at all, so this must not assume it exists.
    """
    external = trip.external_journeys.first()
    return (external.shape if external else '') or ''


def trim_shape(encoded: str, board, alight) -> str:
    """Slice a trip's polyline down to the segment between two stop times.

    Nearest-vertex projection rather than true perpendicular projection onto the
    segments: at the measured 24 m vertex spacing the two differ by at most ~12 m,
    which is finer than the stop positions being matched against and far finer
    than anything visible at map zoom.

    Returns '' rather than a guess when the shape is missing, implausible, or
    does not appear to describe the same journey as these stops -- a wrong line
    on a map is worse than no line, because the rider believes it.
    """
    if not encoded:
        return ''

    points = decode_polyline(encoded)
    if not is_plausible_route_coordinates(points):
        return ''

    board_position = stop_time_position(board)
    alight_position = stop_time_position(alight)
    if board_position is None or alight_position is None:
        return ''

    start, start_distance = _nearest_index(points, *board_position)
    end, end_distance = _nearest_index(points, *alight_position)

    if max(start_distance, end_distance) > MAX_STOP_TO_SHAPE_KM:
        return ''

    if start == end:
        # The whole ride collapsed onto one vertex. Nothing to draw, and
        # returning a single point would render as an invisible zero-length line.
        return ''

    # A trip that doubles back can put the alight vertex before the board one.
    # The rider still travels forward; the slice is simply the other way round.
    if start > end:
        start, end = end, start

    return encode_polyline(points[start:end + 1])


def leg_geometry(trip, board, alight) -> dict:
    """Everything a map needs for one ride: the path, and the stops along it.

    `shape` is '' whenever we cannot honestly draw the road. The stops are still
    returned, so a caller can decide what to do with them -- but on the legacy
    dataset there is no pole either, and the client is not offered a map at all.
    """
    stop_times = sorted(trip.stop_times.all(), key=lambda st: st.sequence)
    segment = [
        st for st in stop_times
        if board.sequence <= st.sequence <= alight.sequence
    ]

    stops = []
    for stop_time in segment:
        position = stop_time_position(stop_time)
        external = getattr(stop_time, 'external_stop', None)
        row = {
            'stopId': stop_time.stop_id,
            'name': stop_time.stop.name,
            'time': stop_time.departure_time.strftime('%Hh%M'),
            'sequence': stop_time.sequence,
            'dayOffset': stop_time.day_offset,
        }
        if position is not None:
            row['lat'], row['lon'] = position
        if external is not None:
            row['code'] = external.code
        stops.append(row)

    return {
        'tripId': trip.id,
        'route': trip.line.code,
        'shape': trim_shape(trip_shape(trip), board, alight),
        'stops': stops,
    }


def line_shapes(line) -> list[dict]:
    """One representative path per direction for a whole line.

    A line has hundreds of trips and they share a route, so drawing "line 110"
    means picking one. The LONGEST decoded path wins per direction: short trips
    are the ones that turn back early or skip a seasonal branch, and a rider
    looking at a line map wants the full extent of it, not the school-run
    variant that stops halfway.

    Empty on legacy, which stores no shapes at all.
    """
    from azoresbus.models import ExternalJourney

    journeys = (
        ExternalJourney.objects
        .filter(trip__line=line, dataset=line.dataset)
        .exclude(shape='')
        .values_list('direction', 'shape', 'trip_id')
    )

    best: dict[int, tuple[int, str, int]] = {}
    for direction, shape, trip_id in journeys:
        points = decode_polyline(shape)
        if not is_plausible_route_coordinates(points):
            continue
        current = best.get(direction)
        # Point count stands in for extent: same encoding, same ~24 m spacing,
        # so more vertices is a longer road. Cheaper than measuring every path.
        if current is None or len(points) > current[0]:
            best[direction] = (len(points), shape, trip_id)

    return [
        {'direction': direction, 'shape': shape, 'tripId': trip_id}
        for direction, (_, shape, trip_id) in sorted(best.items())
    ]


def line_stops(line) -> list[dict]:
    """The stops of the line's fullest trip per direction, in running order.

    Tied to the SAME trip whose shape is returned, so the pins sit on the path
    rather than describing a different variant of the route.
    """
    from transit.models import StopTime

    out = []
    for entry in line_shapes(line):
        stop_times = (
            StopTime.objects.filter(trip_id=entry['tripId'])
            .select_related('stop', 'external_stop')
            .order_by('sequence')
        )
        out.append({
            'direction': entry['direction'],
            'tripId': entry['tripId'],
            'stops': [
                {
                    'stopId': st.stop_id,
                    'name': st.stop.name,
                    'sequence': st.sequence,
                    **(
                        {'lat': st.external_stop.latitude,
                         'lon': st.external_stop.longitude,
                         'code': st.external_stop.code}
                        if st.external_stop is not None
                        else {'lat': st.stop.latitude, 'lon': st.stop.longitude}
                    ),
                }
                for st in stop_times
            ],
        })
    return out
