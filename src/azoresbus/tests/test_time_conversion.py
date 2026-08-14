"""98 B2: night times WRAP below 86400; they never exceed it.

The plan's original converter used `divmod(seconds, 86400)`. That branch never
fires -- the capture confirms the maximum `departureTime` anywhere is 86341.
Past midnight is encoded as a wrap to zero *within one journey*, so the only
correct detector is a DECREASE along `sequence`.

Storing 00:10 without a day offset and then ordering by a bare TimeField
reorders the trip: N03 journey 984 would put its 00:10 stop before its 23:15
one. Every sort must use (day_offset, departure_time) or sequence.
"""

from __future__ import annotations

import json
from datetime import time
from pathlib import Path

from django.test import SimpleTestCase

from azoresbus.services_calendar import circulations_to_stop_times


FIXTURES = Path(__file__).parent / 'fixtures'


def load_journey(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


class WrapDetectionTests(SimpleTestCase):
    """Driven by the real N03 journey 984 payload."""

    def setUp(self):
        self.journey = load_journey('journey_53_984.json')
        self.rows = list(circulations_to_stop_times(self.journey['circulations']))

    def test_nothing_upstream_exceeds_86400(self):
        """The premise. If this ever fails, revisit the whole approach."""
        times = [c['departureTime'] for c in self.journey['circulations']]
        self.assertLessEqual(max(times), 86400)
        self.assertEqual(max(times), 86341, 'the value 98 B2 measured')

    def test_wrap_is_detected_at_the_decrease(self):
        by_sequence = {row['sequence']: row for row in self.rows}

        self.assertEqual(by_sequence[42]['day_offset'], 0)
        self.assertEqual(by_sequence[42]['departure_time'], time(23, 59, 1))

        # seq 43 departs at 0 -- midnight of the NEXT day, not 00:00 of this one.
        self.assertEqual(by_sequence[43]['day_offset'], 1)
        self.assertEqual(by_sequence[43]['departure_time'], time(0, 0))

        self.assertEqual(by_sequence[47]['day_offset'], 1)
        self.assertEqual(by_sequence[47]['departure_time'], time(0, 10))

    def test_offset_never_decreases_along_the_trip(self):
        offsets = [row['day_offset'] for row in self.rows]
        self.assertEqual(offsets, sorted(offsets))
        self.assertEqual(offsets[0], 0)
        self.assertEqual(offsets[-1], 1)

    def test_ordering_by_time_alone_would_corrupt_the_trip(self):
        """The regression this whole mechanism exists to prevent."""
        by_time_only = sorted(self.rows, key=lambda r: r['departure_time'])
        by_offset_then_time = sorted(
            self.rows, key=lambda r: (r['day_offset'], r['departure_time'])
        )
        correct = sorted(self.rows, key=lambda r: r['sequence'])

        self.assertEqual(
            [r['sequence'] for r in by_offset_then_time],
            [r['sequence'] for r in correct],
            '(day_offset, time) must reproduce sequence order',
        )
        self.assertNotEqual(
            [r['sequence'] for r in by_time_only],
            [r['sequence'] for r in correct],
            'fixture no longer exercises the reordering bug',
        )

    def test_every_stop_is_preserved(self):
        self.assertEqual(len(self.rows), len(self.journey['circulations']))


class NotAWrapTests(SimpleTestCase):
    """A journey that STARTS at 00:00 is a separate journey, not a continuation.

    98 B2: N02 has a journey with startTime 0 / endTime 3900 sitting beside
    21:50 and 22:55 journeys. N02 is route 52, outside the capture allowlist, so
    these circulations are synthetic -- the shape is from 98 B2, not invented.
    """

    def test_midnight_start_stays_offset_zero(self):
        circulations = [
            {'sequence': 1, 'departureTime': 0},
            {'sequence': 2, 'departureTime': 900},
            {'sequence': 3, 'departureTime': 2400},
            {'sequence': 4, 'departureTime': 3900},
        ]
        rows = list(circulations_to_stop_times(circulations))
        self.assertEqual([r['day_offset'] for r in rows], [0, 0, 0, 0])
        self.assertEqual(rows[0]['departure_time'], time(0, 0))
        self.assertEqual(rows[-1]['departure_time'], time(1, 5))

    def test_equal_times_are_not_a_wrap(self):
        """Consecutive stops can share a departure time; only a DECREASE wraps."""
        circulations = [
            {'sequence': 1, 'departureTime': 3600},
            {'sequence': 2, 'departureTime': 3600},
            {'sequence': 3, 'departureTime': 3660},
        ]
        rows = list(circulations_to_stop_times(circulations))
        self.assertEqual([r['day_offset'] for r in rows], [0, 0, 0])

    def test_input_order_does_not_matter(self):
        """Upstream ordering is not guaranteed; sequence is the truth."""
        circulations = [
            {'sequence': 3, 'departureTime': 600},
            {'sequence': 1, 'departureTime': 83700},
            {'sequence': 2, 'departureTime': 86341},
        ]
        rows = list(circulations_to_stop_times(circulations))
        self.assertEqual([r['sequence'] for r in rows], [1, 2, 3])
        self.assertEqual([r['day_offset'] for r in rows], [0, 0, 1])
