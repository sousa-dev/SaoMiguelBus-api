"""Where a rider may change buses, and how long the change costs.

A NEIGHBOUR MAP, deliberately not a clustering. Single-link clustering chains:
if A is near B and B is near C, A and C land in one group even when they are
500 m apart, which in a town centre merges a whole street into one "interchange"
and invents connections nobody can make. A neighbour map asks the only question
that matters -- "standing at s1, which stops can I reach, and in how long?" --
and never chains.

Not `build_area_index` either. That grouping is AzoresBus-only and name-based
(`azoresbus/services_stops.py`): it keys on the "VILLAGE (LANDMARK)" convention,
which legacy stop names do not follow. Distance works on both datasets.

The output feeds a two-round scan whose results must match the app's TypeScript
port byte for byte (`matcher.py` docstring). So every ordering here is fixed and
none of it may depend on dict iteration order or on what the DB happened to
return: stops are consumed sorted by id, neighbours are emitted sorted by
`(minutes, stop_id)`.
"""

from __future__ import annotations

from collections import defaultdict

from azoresbus.services_stops import haversine_m

# A stop close enough to walk to while changing buses. 250 m is a little over
# the 100 m `HINT_SPAN_M` the pole-collapse already treats as walkable, and
# comfortably covers a terminal whose arrival and departure bays carry different
# stop names -- the exact case that decides whether Capelas -> Furnas connects.
TRANSFER_RADIUS_M = 250.0

# ~4 km/h. Slow on purpose: the rider is carrying luggage and does not know the
# terminal.
WALK_SPEED_M_PER_MIN = 67.0

# Buffer on top of the walk, applied even when changing at the same stop. A rural
# timetable is not honest to the minute, and a connection we advertise with a
# 1-minute margin is one the rider misses.
MIN_TRANSFER_MINUTES = 5

# Below this much SLACK -- time left standing at the boarding stop once the walk
# is done -- the change is worth warning about.
#
# Measured on slack, not on the raw wait, because they are not the same thing: a
# 12-minute wait with a 9-minute walk leaves three minutes, while 12 minutes at
# the stop you are already standing at leaves twelve. Subtracting the walk means
# the harder change is flagged harder without a second rule to say so.
#
# The consequence of missing a connection here is not a ten-minute wait for the
# next one. On the real network the following bus is often hours later, and on
# some pairs it is the next day -- so the threshold is deliberately generous
# rather than tuned to how often it fires.
TIGHT_TRANSFER_MINUTES = 30

# Degrees of latitude per TRANSFER_RADIUS_M, used as the grid cell size. Longitude
# cells are the same width in degrees, which makes them NARROWER in metres at
# 37.7 N -- so the grid over-collects candidates and the haversine check below
# rejects them. Over-collecting is correct; under-collecting would silently drop
# connections.
_METRES_PER_DEGREE_LAT = 111_320.0


def _cell(latitude: float, longitude: float, size_deg: float) -> tuple[int, int]:
    return (int(latitude // size_deg), int(longitude // size_deg))


def has_usable_position(latitude, longitude) -> bool:
    """Reject coordinates that would invent interchanges.

    Null Island is the failure that matters. Two stops with missing coordinates
    both land at (0, 0), measure zero metres apart, and the scan cheerfully
    offers a change between two villages 40 km apart -- the single worst thing
    this feature can do, because a rider acts on it and is stranded.

    Cheap to check, and it only ever removes a stop from the INTERCHANGE set:
    the stop still appears in searches and still carries riders, it just cannot
    be a place we tell someone to change buses.
    """
    if latitude is None or longitude is None:
        return False
    try:
        latitude, longitude = float(latitude), float(longitude)
    except (TypeError, ValueError):
        return False
    if latitude != latitude or longitude != longitude:   # NaN
        return False
    if latitude == 0.0 and longitude == 0.0:
        return False
    return -90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0


def walk_minutes(distance_m: float) -> int:
    """Whole minutes to walk `distance_m`, rounded up. Zero distance costs zero."""
    if distance_m <= 0:
        return 0
    return int(-(-distance_m // WALK_SPEED_M_PER_MIN))


def transfer_minutes(distance_m: float) -> int:
    return MIN_TRANSFER_MINUTES + walk_minutes(distance_m)


def transfer_neighbours(stops) -> dict[int, list[tuple[int, int]]]:
    """`stop_id -> [(reachable_stop_id, minutes), ...]`, always including itself.

    `stops` is any iterable of objects with `id`, `latitude`, `longitude`.

    Grid-bucketed, so this is O(n) in the stop count rather than O(n^2): at 816
    stops the naive form is 665k haversine calls on every search request.
    """
    size_deg = TRANSFER_RADIUS_M / _METRES_PER_DEGREE_LAT

    rows = sorted(
        ((stop.id, stop.latitude, stop.longitude) for stop in stops),
        key=lambda row: row[0],
    )

    # Only stops we can actually locate take part in the DISTANCE search. A stop
    # keeps its own entry either way: changing buses at the stop you are already
    # standing at needs no geometry.
    locatable = [row for row in rows if has_usable_position(row[1], row[2])]

    buckets: dict[tuple[int, int], list[tuple[int, float, float]]] = defaultdict(list)
    for row in locatable:
        buckets[_cell(row[1], row[2], size_deg)].append(row)

    usable = {row[0] for row in locatable}

    neighbours: dict[int, list[tuple[int, int]]] = {}
    for stop_id, latitude, longitude in rows:
        found: list[tuple[int, int]] = [(stop_id, MIN_TRANSFER_MINUTES)]

        if stop_id in usable:
            cell_lat, cell_lon = _cell(latitude, longitude, size_deg)
            for d_lat in (-1, 0, 1):
                for d_lon in (-1, 0, 1):
                    for other_id, other_lat, other_lon in buckets.get(
                        (cell_lat + d_lat, cell_lon + d_lon), (),
                    ):
                        if other_id == stop_id:
                            continue
                        distance = haversine_m(latitude, longitude, other_lat, other_lon)
                        if distance <= TRANSFER_RADIUS_M:
                            found.append((other_id, transfer_minutes(distance)))

        found.sort(key=lambda entry: (entry[1], entry[0]))
        neighbours[stop_id] = found

    return neighbours
