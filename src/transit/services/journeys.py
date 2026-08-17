"""Origin -> destination journeys, with at most one change of bus.

`search_routes` answers "which single trip serves both ends?". That is the right
question for 90% of searches and the wrong one for Capelas -> Furnas, which no
single line runs -- it returned an empty list and the app said no route exists.

This module answers "how do I get there?" instead, bounded at ONE transfer. The
bound is a product decision, not a limitation of the scan: San Miguel's network
is hub-and-spoke through Ponta Delgada, so a second change buys almost no real
journeys while multiplying the candidates to rank and offering itineraries that
a rural timetable cannot honour.

WHY A PROFILE SCAN, NOT AN EARLIEST-ARRIVAL QUERY
The app searches the whole day -- `FULL_DAY_START = '00h00'` in
`useOfflineSearch.ts` -- and reorders client-side around the user's clock. So
this cannot collapse to "best arrival per stop" the way a RAPTOR round would;
every departure across the service day has to survive to the ranking step.

Two rounds, joined on a transfer point:

    round A   every (board at origin -> alight anywhere later) on one trip
    round B   every (board anywhere earlier -> alight at destination) on one trip
    join      A.alight and B.board within walking distance, B departing late
              enough that the change is actually makeable

Cost is bounded by the trips that touch either endpoint -- around 30 per village
times ~25 later stops, so ~750 events a side, then one binary search per event.
The DB work is the query `search_routes` already runs.

PARITY
`lib/journey-search.ts` in the Expo app is a port of this file and must produce
identical output for identical input, for the same reason `matcher.py` gives:
the two disagreeing is invisible until a user compares online and offline
results for the same search. Every ordering below is total and explicit -- never
dict iteration order, never a bare queryset order.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, time

from azoresbus.services_stops import build_area_index
from tenancy.services import get_active_island
from transit.models import DATASET_AZORESBUS, Holiday, Stop, Trip
from transit.services.legacy_import import clean_string
from transit.services.matcher import absolute_minutes as stop_time_minutes
from transit.services.matcher import select_pair
from transit.services.schedule_phase import resolve_dataset
from transit.services.search import (
    _type_of_day_for,
    _trip_dislikes_percent,
    _trip_likes_percent,
    eligible_trips,
    get_type_of_day,
    normalize_origin,
    parse_time_parts,
    resolve_stop_ids,
)
from transit.services.transfer_points import transfer_neighbours

# Transfer journeys returned per search, after pruning. Direct journeys are never
# capped: a rider scrolling for a later bus must not lose one to a cap spent on
# itineraries with a change in them.
MAX_TRANSFER_JOURNEYS = 12

# The most changes of bus this scan can plan. One, deliberately -- see the module
# docstring. Callers clamp to it rather than trusting a client-supplied number.
MAX_SUPPORTED_TRANSFERS = 1

# Candidate second buses considered per interchange, per first leg. The first
# catchable departure is usually the answer, but not always -- see
# `_transfer_journeys`.
CONNECTIONS_PER_INTERCHANGE = 3

# A wait long enough that this stops being one journey.
#
# Pareto dominance alone does not catch these, and production showed exactly why:
# a Capelas -> Ponta Delgada itinerary rode 2 minutes to the next stop in the SAME
# village at 00h53, waited 5h29, then took the 06h24 bus. Nothing dominated it --
# it departs earlier than every other option -- but no rider wants it, they want
# the 06h36 direct.
#
# Two rules, because one is not enough:
#
#   ratio     waiting 2h for a 4h journey is a connection; waiting 2h for a
#             10-minute hop is not. Scaling by the time actually spent riding is
#             what separates the two, and it is what kills the 00h53 case
#             (329 min wait against 36 min of riding, 9x).
#   absolute  a ceiling for long journeys, where the ratio alone stays generous.
#
# Tuned against real São Miguel data, NOT picked round: Saturday's only
# Capelas -> Furnas connection waits 241 minutes and Sunday's waits 136. Both are
# genuinely the sole option that day, so a tighter cap would put those pairs back
# to "no connection" -- the exact falsehood this feature exists to remove.
MAX_TRANSFER_WAIT_MINUTES = 300
MAX_WAIT_TO_RIDE_RATIO = 3


@dataclass(frozen=True)
class Leg:
    """One ride: board and alight `StopTime` rows on a single trip."""

    trip: Trip
    board: object
    alight: object

    @property
    def departure(self) -> int:
        return stop_time_minutes(self.board)

    @property
    def arrival(self) -> int:
        return stop_time_minutes(self.alight)


@dataclass(frozen=True)
class Journey:
    legs: tuple[Leg, ...]
    #: Minutes spent at the interchange, walking included. Empty for direct.
    waits: tuple[int, ...]

    @property
    def departure(self) -> int:
        return self.legs[0].departure

    @property
    def arrival(self) -> int:
        return self.legs[-1].arrival

    @property
    def transfers(self) -> int:
        return len(self.legs) - 1

    @property
    def key(self) -> tuple[int, ...]:
        return tuple(leg.trip.id for leg in self.legs)


def resolve_service_day(day: str) -> tuple[str, object | None]:
    """`day` -> (service type, date to resolve against or None).

    Lifted out of the scan because the serializer needs the SAME answer: a
    journey on 2026-08-15 is a Saturday, and labelling it WEEKDAY because the
    caller only had the raw string is the kind of drift this codebase keeps
    paying for. Mirrors `search_routes` exactly, holiday branch included.
    """
    if day and '-' in day:
        try:
            parsed = datetime.strptime(day, '%Y-%m-%d')
            on_date = parsed.date()
            is_holiday = Holiday.objects.filter(date=on_date).exists()
            service_type = get_type_of_day(parsed, is_holiday)
            # Upstream resolves a holiday to its Sunday set, so eligibility is
            # evaluated as a Sunday rather than by the calendar weekday.
            return service_type, (None if is_holiday else on_date)
        except ValueError:
            return day.upper(), None
    return day.upper(), None


def _ordered_stop_times(trip: Trip) -> list:
    """Never sort by a bare TimeField -- a night trip would reorder (98 B2)."""
    cached = getattr(trip, '_journey_stop_times', None)
    if cached is None:
        cached = sorted(trip.stop_times.all(), key=lambda st: st.sequence)
        trip._journey_stop_times = cached
    return cached


def _advances_in_time(board, alight) -> bool:
    """Does this ride actually move the rider FORWARD?

    Legacy timetables contain trips whose times go backwards mid-route: line 206
    reaches sequence 12 at 08h20 and sequence 13 at 08h10, with no `day_offset`
    to explain it. `/transit/search` has shipped those rows for years (3 of 37 on
    one Ponta Delgada query) and they are merely odd there -- one trip, one wrong
    end time.

    In a journey they are corrosive: a leg that arrives before it departs makes
    `durationMinutes` a lie and lets a connection satisfy the transfer buffer
    against a time the bus never reaches. Sequence order alone cannot catch it,
    because the sequence IS in order -- only the clock disagrees.
    """
    return stop_time_minutes(alight) > stop_time_minutes(board)


def _legs_from_origin(trips, origin_ids: set[int]) -> list[Leg]:
    """Every ride that STARTS at the origin, alighting anywhere later.

    Every alight is kept, not just the best one: which is best depends on what
    departs from there, which round B has not been joined yet.
    """
    legs: list[Leg] = []
    for trip in trips:
        stop_times = _ordered_stop_times(trip)
        for index, board in enumerate(stop_times):
            if board.stop_id not in origin_ids:
                continue
            for alight in stop_times[index + 1:]:
                if _advances_in_time(board, alight):
                    legs.append(Leg(trip=trip, board=board, alight=alight))
    return legs


def _legs_to_destination(trips, destination_ids: set[int]) -> list[Leg]:
    """Every ride that ENDS at the destination, boarding anywhere earlier."""
    legs: list[Leg] = []
    for trip in trips:
        stop_times = _ordered_stop_times(trip)
        for index, alight in enumerate(stop_times):
            if alight.stop_id not in destination_ids:
                continue
            for board in stop_times[:index]:
                if _advances_in_time(board, alight):
                    legs.append(Leg(trip=trip, board=board, alight=alight))
    return legs


def _index_by_board_stop(legs: list[Leg]) -> dict[int, tuple[list[int], list[Leg]]]:
    """`stop_id -> (sorted departure minutes, legs in that order)`.

    Sorted so the join can binary-search the first bus a rider can still catch
    instead of rescanning every leg B for every leg A.
    """
    grouped: dict[int, list[Leg]] = {}
    for leg in legs:
        grouped.setdefault(leg.board.stop_id, []).append(leg)

    index: dict[int, tuple[list[int], list[Leg]]] = {}
    for stop_id, rows in grouped.items():
        rows.sort(key=lambda leg: (leg.departure, leg.arrival, leg.trip.id, leg.board.sequence))
        index[stop_id] = ([leg.departure for leg in rows], rows)
    return index


def _direct_journeys(
    trips, origin_ids: set[int], destination_ids: set[int], earliest,
) -> list[Journey]:
    """Direct rides -- one per trip, via the SAME `select_pair` search uses.

    Not "every valid (board, alight) pair": on a loop that touches the origin
    twice, that would list the same bus repeatedly, and it would put rows in
    `/journeys` that `/search` does not return for the same query. `select_pair`
    owns the tie-break (earliest board, then shortest ride, then stable) and it
    has to stay the one place that decides it.
    """
    journeys: list[Journey] = []
    for trip in trips:
        pair = select_pair(trip, origin_ids, destination_ids, earliest=earliest)
        if pair is None:
            continue
        board, alight = pair
        if not _advances_in_time(board, alight):
            continue
        journeys.append(
            Journey(legs=(Leg(trip=trip, board=board, alight=alight),), waits=()),
        )
    return journeys


def _wait_is_reasonable(journey: Journey) -> bool:
    """Is this still one journey, or two trips with a day in between?"""
    wait = sum(journey.waits)
    if wait == 0:
        return True
    if wait > MAX_TRANSFER_WAIT_MINUTES:
        return False
    riding = sum(leg.arrival - leg.departure for leg in journey.legs)
    return wait <= riding * MAX_WAIT_TO_RIDE_RATIO


def _transfer_journeys(
    first_legs: list[Leg],
    second_index: dict[int, tuple[list[int], list[Leg]]],
    neighbours: dict[int, list[tuple[int, int]]],
    destination_ids: set[int],
) -> list[Journey]:
    """Join round A to round B at every reachable interchange."""
    journeys: list[Journey] = []

    for first in first_legs:
        if first.alight.stop_id in destination_ids:
            # Already there -- this is a direct ride, not a transfer.
            continue

        for stop_id, cost in neighbours.get(first.alight.stop_id, ()):
            entry = second_index.get(stop_id)
            if entry is None:
                continue
            departures, legs = entry

            earliest = first.arrival + cost
            position = bisect_left(departures, earliest)

            taken = 0
            for second in legs[position:]:
                if second.trip.line_id == first.trip.line_id:
                    # The same line is the same bus continuing, not a change.
                    # Riders do not get off and back on, and offering it as a
                    # transfer makes a one-bus ride look like two. Skip PAST it
                    # rather than abandoning this interchange -- the next
                    # departure may well be the connection that works.
                    continue

                journeys.append(
                    Journey(
                        legs=(first, second),
                        waits=(second.departure - first.arrival,),
                    ),
                )

                # A few departures, not just the first: the second bus out may
                # be an express that overtakes it, and only the Pareto prune can
                # tell. Beyond a handful it is all dominated anyway.
                taken += 1
                if taken >= CONNECTIONS_PER_INTERCHANGE:
                    break

    return journeys


def _collapse_by_trip_pair(journeys: list[Journey]) -> list[Journey]:
    """One journey per set of trips -- the tightest connection between them.

    Many round-A alight points feed the same pair of trips (every stop the first
    bus passes where the second is still catchable). They are one itinerary to a
    rider, so keep the one that leaves latest and arrives earliest.
    """
    best: dict[tuple[int, ...], Journey] = {}
    for journey in journeys:
        current = best.get(journey.key)
        rank = (journey.arrival, -journey.departure, journey.legs[0].board.sequence)
        if current is None or rank < (
            current.arrival, -current.departure, current.legs[0].board.sequence,
        ):
            best[journey.key] = journey
    return list(best.values())


def _prune_dominated(journeys: list[Journey]) -> list[Journey]:
    """Drop any journey another one beats on every axis at once.

    A journey is dominated when some other leaves no earlier, arrives no later,
    and changes bus no more often -- there is no reason a rider would pick it.
    This is what stops a three-hour two-bus itinerary sitting next to the direct
    bus that leaves at the same time and beats it.

    Sorted first so the comparison is against a stable order, then O(n^2) over a
    list that pruning and the cap keep small.
    """
    ordered = sorted(journeys, key=_sort_key)
    kept: list[Journey] = []

    for index, journey in enumerate(ordered):
        dominated = False
        for other_index, other in enumerate(ordered):
            if other_index == index:
                continue
            if (
                other.departure >= journey.departure
                and other.arrival <= journey.arrival
                and other.transfers <= journey.transfers
            ):
                # Equal on all three: keep whichever sorts first, drop the rest,
                # or they would eliminate each other.
                if (
                    other.departure == journey.departure
                    and other.arrival == journey.arrival
                    and other.transfers == journey.transfers
                ):
                    if other_index < index:
                        dominated = True
                        break
                    continue
                dominated = True
                break
        if not dominated:
            kept.append(journey)

    return kept


def _sort_key(journey: Journey) -> tuple:
    return (
        journey.departure,
        journey.arrival,
        journey.transfers,
        journey.key,
    )


def search_journeys(
    *,
    origin: str,
    destination: str,
    day: str,
    start_time: str,
    dataset: str | None = None,
    max_transfers: int = MAX_SUPPORTED_TRANSFERS,
) -> list[Journey] | None:
    """Direct rides and one-transfer itineraries, ranked. `None` on a bad query.

    `max_transfers=0` restricts the answer to a single bus. Riders with luggage,
    a pushchair or a tight schedule do not want to be told to change at a rural
    terminal, and for them a two-bus itinerary is noise rather than an option.
    It is also strictly cheaper: the transfer scan, the leg enumeration and the
    interchange map are all skipped rather than computed and filtered away.

    Resolution of stops, dataset and service days is deliberately the SAME code
    `search_routes` uses. A journey offered here that search would not have
    offered directly would mean the two disagree about which buses run.
    """
    origin = normalize_origin(origin)
    if not origin or not destination:
        return None

    origin_cleaned = clean_string(origin)
    destination_cleaned = clean_string(destination)

    service_type, on_date = resolve_service_day(day)

    start_hour, start_minute = parse_time_parts(start_time.replace('h', ':'))
    earliest_departure = start_hour * 60 + start_minute

    if dataset is None:
        dataset = resolve_dataset(get_active_island(), on_date=on_date)

    stops = list(Stop.objects.filter(dataset=dataset).only(
        'id', 'name', 'latitude', 'longitude',
    ))

    area_index = (
        build_area_index(stops) if dataset == DATASET_AZORESBUS else None
    )

    origin_ids = resolve_stop_ids(dataset, origin_cleaned, area_index)
    destination_ids = resolve_stop_ids(dataset, destination_cleaned, area_index)
    if not origin_ids or not destination_ids:
        return []

    # Somewhere to itself is not a journey. Production answered
    # "Capelas -> Capelas" with 12 itineraries that rode to the next stop in the
    # village and came back. Compared as SETS, so this only catches a query that
    # resolves to the same place on both sides -- "Capelas (Igreja)" to
    # "Capelas (Moagem)" is a real, if short, ride and still works.
    if origin_ids == destination_ids:
        return []

    trips = list(
        eligible_trips(
            Trip.objects.filter(
                source=Trip.SOURCE_OPERATOR, line__disabled=False, dataset=dataset,
            ),
            day_type=service_type,
            on_date=on_date,
        )
        .select_related('line', 'calendar', 'service')
        .prefetch_related('stop_times__stop', 'stop_times__external_stop')
        .order_by('id')
    )

    # Same `time`-or-None shape `search_routes` passes, so a direct row here is
    # the same row `/search` returns for the same query.
    earliest = (
        time(start_hour, start_minute) if (start_hour or start_minute) else None
    )
    direct = _direct_journeys(trips, origin_ids, destination_ids, earliest)

    transfers: list[Journey] = []
    if max_transfers >= 1:
        first_legs = _legs_from_origin(trips, origin_ids)
        second_index = _index_by_board_stop(
            _legs_to_destination(trips, destination_ids),
        )
        neighbours = transfer_neighbours(stops)
        transfers = [
            journey for journey in _collapse_by_trip_pair(
                _transfer_journeys(
                    first_legs, second_index, neighbours, destination_ids,
                ),
            )
            if _wait_is_reasonable(journey)
        ]

    candidates = [
        journey for journey in direct + transfers
        if journey.departure >= earliest_departure
    ]
    kept = _prune_dominated(candidates)

    # The cap applies only to transfer journeys, so a long tail of itineraries
    # with a change cannot push a later direct bus off the list.
    direct_kept = [journey for journey in kept if journey.transfers == 0]
    transfer_kept = [journey for journey in kept if journey.transfers > 0]
    transfer_kept = sorted(transfer_kept, key=_sort_key)[:MAX_TRANSFER_JOURNEYS]

    return sorted(direct_kept + transfer_kept, key=_sort_key)


def journey_service_day(journey: Journey, service_type: str | None) -> str:
    return _type_of_day_for(journey.legs[0].trip, service_type)


def leg_vote_percents(leg: Leg) -> tuple[int, int]:
    return _trip_likes_percent(leg.trip), _trip_dislikes_percent(leg.trip)
