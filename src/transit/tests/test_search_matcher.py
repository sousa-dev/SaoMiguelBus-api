"""98 B7 / 02 §3.4: match on sequence, not string position.

On a loop A -> B -> C -> D -> A, searching C -> A finds A at index 0, concludes
the origin comes after the destination, and discards a valid trip. Three of our
implementations do exactly that.

The tie-break is identical on server, offline client and webapp or results
diverge: earliest BOARD time, then shortest ELAPSED DURATION, then trip id.
Never stop count -- on 335, with 36 repeated names, fewest-stops selects a
one-stop hop that is not the ride anyone wanted.
"""

from __future__ import annotations

from datetime import time

from django.test import TestCase

from tenancy.services import get_or_create_default_island
from transit.models import (
    DATASET_AZORESBUS,
    Line,
    Operator,
    ServicePattern,
    Stop,
    StopTime,
    Trip,
)
from transit.services.matcher import select_pair, valid_pairs


class MatcherFixture(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        self.operator, _ = Operator.objects.get_or_create(
            island=self.island, name='AzoresBus', defaults={'contact': {}},
        )
        self.pattern = ServicePattern.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, key='everyday',
            monday=True, tuesday=True, wednesday=True, thursday=True,
            friday=True, saturday=True, sunday=True,
        )
        self.stops = {}

    def stop(self, name: str) -> Stop:
        if name not in self.stops:
            self.stops[name] = Stop.objects.create(
                island=self.island, dataset=DATASET_AZORESBUS,
                name=name, cleaned_name=name.lower(),
                latitude=37.7, longitude=-25.6,
            )
        return self.stops[name]

    def trip(self, code: str, stops: list[tuple[str, str, int]]) -> Trip:
        """stops: (name, 'HH:MM', day_offset)."""
        line = Line.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, code=code,
            operator=self.operator,
        )
        trip = Trip.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, line=line,
            service=self.pattern, source=Trip.SOURCE_OPERATOR,
        )
        for index, (name, hhmm, offset) in enumerate(stops, start=1):
            hour, minute = (int(part) for part in hhmm.split(':'))
            StopTime.objects.create(
                island=self.island, trip=trip, stop=self.stop(name),
                sequence=index, departure_time=time(hour, minute),
                day_offset=offset,
            )
        return trip


class LoopTests(MatcherFixture):
    """301 is a real loop: first and last stop share a name."""

    def setUp(self):
        super().setUp()
        self.loop = self.trip('301', [
            ('ALFA', '06:00', 0),
            ('BRAVO', '06:30', 0),
            ('CHARLIE', '07:00', 0),
            ('DELTA', '07:30', 0),
            ('ALFA', '08:00', 0),
        ])

    def test_the_later_leg_of_a_loop_is_found(self):
        pairs = valid_pairs(
            self.loop, self.stop('CHARLIE').id, self.stop('ALFA').id,
        )
        self.assertEqual(len(pairs), 1)
        board, alight = pairs[0]
        self.assertEqual((board.sequence, alight.sequence), (3, 5))

    def test_first_occurrence_matching_would_have_dropped_it(self):
        """The bug this replaces, stated as a property of the fixture."""
        names = [
            st.stop.name
            for st in self.loop.stop_times.order_by('sequence')
        ]
        self.assertLess(
            names.index('ALFA'), names.index('CHARLIE'),
            'fixture no longer exercises the loop bug',
        )

    def test_riding_the_full_loop_is_a_valid_pair(self):
        """ALFA -> ALFA advances from seq 1 to seq 5, so it is a real ride.

        Rejecting origin == destination is a search-level concern, not the
        matcher's: what the matcher owes is "board precedes alight".
        """
        pairs = valid_pairs(
            self.loop, self.stop('ALFA').id, self.stop('ALFA').id,
        )
        self.assertEqual([(b.sequence, a.sequence) for b, a in pairs], [(1, 5)])

    def test_a_pair_that_would_travel_backwards_is_not_returned(self):
        pairs = valid_pairs(
            self.loop, self.stop('DELTA').id, self.stop('BRAVO').id,
        )
        self.assertEqual(pairs, [], 'DELTA is never followed by BRAVO')


class TieBreakTests(MatcherFixture):
    def test_earliest_board_wins(self):
        trip = self.trip('A', [
            ('X', '06:00', 0), ('Y', '06:30', 0),
            ('X', '09:00', 0), ('Y', '09:30', 0),
        ])
        board, _ = select_pair(trip, self.stop('X').id, self.stop('Y').id)
        self.assertEqual(board.sequence, 1)

    def test_shortest_elapsed_duration_breaks_a_board_tie(self):
        """From one board time, the leg that arrives soonest wins.

        Both alights are reachable from the 06:00 board, so this isolates the
        duration rule rather than the board-time rule: 45 minutes must beat 120.
        """
        from transit.services.matcher import elapsed_minutes

        trip = self.trip('B', [
            ('X', '06:00', 0),
            ('Y', '08:00', 0),      # slow leg from this board: 120 min
            ('MID', '06:30', 0),
            ('Y', '06:45', 0),      # fast leg from the same board: 45 min
        ])
        board, alight = select_pair(trip, self.stop('X').id, self.stop('Y').id)

        self.assertEqual(board.sequence, 1)
        self.assertEqual(
            elapsed_minutes(board, alight), 45,
            'the longer leg from the same board was selected',
        )
        self.assertEqual(alight.sequence, 4)

    def test_stop_count_is_never_the_tie_break(self):
        """98 §5 challenge 4: fewest-stops picks a one-stop hop on 335."""
        trip = self.trip('C', [
            ('X', '06:00', 0),
            ('MID1', '06:10', 0),
            ('MID2', '06:20', 0),
            ('Y', '06:30', 0),      # 3 stops, 30 minutes
            ('X', '07:00', 0),
            ('Y', '09:00', 0),      # 1 stop, 2 hours
        ])
        board, alight = select_pair(trip, self.stop('X').id, self.stop('Y').id)
        self.assertEqual(
            (board.sequence, alight.sequence), (1, 4),
            'the fewer-stops leg is slower and must not win',
        )

    def test_no_pair_returns_none(self):
        """Y never precedes X on a one-way trip."""
        trip = self.trip('D', [('X', '06:00', 0), ('Y', '06:30', 0)])
        self.assertIsNone(
            select_pair(trip, self.stop('Y').id, self.stop('X').id)
        )


class NightWrapTests(MatcherFixture):
    """Duration and ordering must respect day_offset (98 B2)."""

    def test_a_leg_across_midnight_has_a_positive_duration(self):
        trip = self.trip('N03', [
            ('X', '23:15', 0),
            ('Y', '00:10', 1),
        ])
        board, alight = select_pair(trip, self.stop('X').id, self.stop('Y').id)
        from transit.services.matcher import elapsed_minutes

        self.assertEqual(elapsed_minutes(board, alight), 55)

    def test_a_wrapped_leg_does_not_beat_an_earlier_same_day_one(self):
        trip = self.trip('N05', [
            ('X', '22:00', 0),
            ('Y', '22:30', 0),
            ('X', '23:50', 0),
            ('Y', '00:20', 1),
        ])
        board, _ = select_pair(trip, self.stop('X').id, self.stop('Y').id)
        self.assertEqual(board.sequence, 1)


class BoardTimeFilterTests(MatcherFixture):
    """02 §3.4: filter on the SELECTED board stop, not the trip's first stop."""

    def test_a_late_board_on_an_early_trip_is_returned(self):
        trip = self.trip('E', [
            ('DEPOT', '06:00', 0),
            ('X', '09:00', 0),
            ('Y', '09:30', 0),
        ])
        board, _ = select_pair(
            trip, self.stop('X').id, self.stop('Y').id,
            earliest=time(8, 30),
        )
        self.assertIsNotNone(
            board, 'today this trip is dropped because it departed at 06:00',
        )
        self.assertEqual(board.sequence, 2)

    def test_a_board_before_the_requested_time_is_excluded(self):
        trip = self.trip('F', [('X', '06:00', 0), ('Y', '06:30', 0)])
        self.assertIsNone(
            select_pair(
                trip, self.stop('X').id, self.stop('Y').id,
                earliest=time(8, 30),
            )
        )

    def test_the_filter_picks_the_first_qualifying_leg_not_the_first_leg(self):
        trip = self.trip('G', [
            ('X', '06:00', 0), ('Y', '06:30', 0),
            ('X', '09:00', 0), ('Y', '09:30', 0),
        ])
        board, _ = select_pair(
            trip, self.stop('X').id, self.stop('Y').id,
            earliest=time(8, 30),
        )
        self.assertEqual(board.sequence, 3)
