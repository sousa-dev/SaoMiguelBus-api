"""Pick the (board, alight) pair for a trip, by sequence.

Resolving a stop by first occurrence is a real bug, not a simplification: on a
loop A -> B -> C -> D -> A, a search for C -> A finds A at index 0, decides the
origin comes after the destination, and throws away a valid trip (98 B7).

Three implementations share it -- `search.py`, `lib/offline-bundle.ts` and the
app's `extractTripSegment` -- so the server fix only helps once the client
honours the sequence indices this returns. That is why the response carries
`boarding.sequence` and `alighting.sequence` (02 §7.1b).

The tie-break must be byte-identical across all three or results diverge:

    1. earliest board  (day_offset, departure_time)
    2. then shortest ELAPSED DURATION, offsets included
    3. then stable trip id

Never stop count. On 335, with 36 repeated names, "fewest stops" can select a
one- or two-stop hop that is not the ride the user asked for (98 §5 challenge 4).

`origin_stop_ids`/`destination_stop_ids` are SETS. A plain stop search passes a
singleton; a village search ("Capelas") passes every stop id sharing that
village's name prefix, so the trip need only touch ONE member on each side --
the caller (`search.py`) already iterates every eligible trip regardless, so
this changes zero DB queries, only a per-StopTime membership test.
"""

from __future__ import annotations

from datetime import time

MINUTES_PER_DAY = 24 * 60


def _minutes(stop_time) -> int:
    """Absolute minutes from the trip's first calendar day."""
    value: time = stop_time.departure_time
    return (
        stop_time.day_offset * MINUTES_PER_DAY
        + value.hour * 60
        + value.minute
    )


def elapsed_minutes(board, alight) -> int:
    """Journey length across a midnight wrap."""
    return _minutes(alight) - _minutes(board)


def _ordered_stop_times(trip) -> list:
    """Never sort by a bare TimeField: N03 984 would reorder (98 B2)."""
    cached = getattr(trip, '_matcher_stop_times', None)
    if cached is None:
        cached = list(trip.stop_times.select_related('stop').order_by('sequence'))
        trip._matcher_stop_times = cached
    return cached


def valid_pairs(trip, origin_stop_ids: set[int], destination_stop_ids: set[int]) -> list:
    """Every (board, alight) on this trip where board precedes alight.

    Resolves by stop id rather than fuzzy substring, which also removes the
    containment mis-hits the string matcher produced (LAGOA matching a trip that
    only serves LAGOA DO FOGO). Each side is a SET: a village search unions
    every stop sharing that village's name prefix, so a trip qualifies the
    moment it touches ANY one member on each side.
    """
    stop_times = _ordered_stop_times(trip)
    origins = [st for st in stop_times if st.stop_id in origin_stop_ids]
    destinations = [st for st in stop_times if st.stop_id in destination_stop_ids]

    return [
        (board, alight)
        for board in origins
        for alight in destinations
        if board.sequence < alight.sequence
    ]


def select_pair(
    trip,
    origin_stop_ids: set[int],
    destination_stop_ids: set[int],
    *,
    earliest: time | None = None,
):
    """The one pair to show for this trip, or None.

    `earliest` filters on the SELECTED BOARD STOP's time. Today search compares
    against the trip's FIRST stop time, so a late board on a loop that departed
    earlier is dropped -- a deliberate behaviour change (02 §3.4).
    """
    pairs = valid_pairs(trip, origin_stop_ids, destination_stop_ids)

    if earliest is not None:
        pairs = [
            pair for pair in pairs
            if (pair[0].day_offset, pair[0].departure_time) >= (0, earliest)
        ]

    if not pairs:
        return None

    return min(
        pairs,
        key=lambda pair: (
            _minutes(pair[0]),                       # earliest board
            elapsed_minutes(*pair),                  # then shortest ride
            pair[0].sequence,                        # then stable
        ),
    )
