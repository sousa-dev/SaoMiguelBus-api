"""1456 upstream stops collapse to 816 transit.Stop rows.

The duplicates are the two sides of a road: median 11.5 m apart, 629 of 630
pairs with consecutive integer codes. A tourist cannot choose a pole before
choosing a destination, so pickers get one row per name and the physical pole
comes back with the result instead (02 §3.2).

Which pole a trip serves is a property of its direction — of route 101's 27
names served both ways, 24 use a different code per direction — so it is kept on
ExternalStop rather than thrown away.

Driven by the real /api/stops payload.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.test import SimpleTestCase

from azoresbus.services_stops import collapse_stops, haversine_m


FIXTURES = Path(__file__).parent / 'fixtures'


def upstream_stops() -> list[dict]:
    return json.loads((FIXTURES / 'stops.json').read_text(encoding='utf-8'))


class HaversineTests(SimpleTestCase):
    def test_zero_distance(self):
        self.assertAlmostEqual(
            haversine_m(37.74, -25.67, 37.74, -25.67), 0.0, places=6,
        )

    def test_known_separation(self):
        """~111 m per 0.001 degrees of latitude."""
        self.assertAlmostEqual(
            haversine_m(37.740, -25.67, 37.741, -25.67), 111.0, delta=1.0,
        )


class CollapseTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.result = collapse_stops(upstream_stops())

    def test_1456_stops_become_816_groups(self):
        self.assertEqual(len(upstream_stops()), 1456)
        self.assertEqual(len(self.result.groups), 816)

    def test_group_membership_matches_98(self):
        sizes = [len(group.members) for group in self.result.groups]
        self.assertEqual(sum(1 for n in sizes if n == 1), 181)
        self.assertEqual(sum(1 for n in sizes if n == 2), 630)
        self.assertEqual(sum(1 for n in sizes if n == 3), 5)
        self.assertEqual(max(sizes), 3)

    def test_every_upstream_stop_lands_in_exactly_one_group(self):
        seen = [member['id'] for group in self.result.groups
                for member in group.members]
        self.assertEqual(len(seen), 1456)
        self.assertEqual(len(set(seen)), 1456)

    def test_centroid_sits_between_its_members(self):
        for group in self.result.groups:
            lats = [float(m['position']['lat']) for m in group.members]
            lons = [float(m['position']['lon']) for m in group.members]
            self.assertGreaterEqual(group.latitude, min(lats))
            self.assertLessEqual(group.latitude, max(lats))
            self.assertGreaterEqual(group.longitude, min(lons))
            self.assertLessEqual(group.longitude, max(lons))


class SeparationFlagTests(SimpleTestCase):
    """02 §3.2 sizes the import review queue off these numbers."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.result = collapse_stops(upstream_stops())

    def test_exactly_14_groups_exceed_75m(self):
        self.assertEqual(
            len(self.result.flagged), 14,
            '02 §3.2 originally said 30; 98 measured 14',
        )

    def test_three_groups_exceed_100m_and_none_exceed_250m(self):
        spans = sorted(
            (group.span_m for group in self.result.groups), reverse=True,
        )
        self.assertEqual(sum(1 for s in spans if s > 100), 3)
        self.assertEqual(sum(1 for s in spans if s > 250), 0)

    def test_the_worst_three_are_the_named_ones(self):
        worst = sorted(self.result.flagged, key=lambda g: -g.span_m)[:3]
        self.assertEqual(
            [g.name for g in worst],
            [
                'COVOADA (AV. 6 DE JANEIRO)',
                'PONTA DELGADA (ALFÂNDEGA)',
                'P. DELGADA (FORTE S. BRÁS)',
            ],
        )
        self.assertAlmostEqual(worst[0].span_m, 164.1, delta=0.5)

    def test_median_and_max_separation(self):
        multi = sorted(
            group.span_m for group in self.result.groups
            if len(group.members) > 1
        )
        median = multi[len(multi) // 2]
        self.assertAlmostEqual(median, 11.5, delta=0.5)
        self.assertAlmostEqual(max(multi), 164.1, delta=0.5)


class PoleCodeTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.result = collapse_stops(upstream_stops())

    def test_non_consecutive_codes_are_not_an_error(self):
        """CAPELAS (LG. TEATRO NOVO) is codes 1268/1270, 18.4 m apart.

        The one non-consecutive pair in the network. It is still a road pair, so
        a skipped integer must not be treated as a collapse failure (98 claim 3).
        """
        group = next(
            g for g in self.result.groups
            if g.name == 'CAPELAS (LG. TEATRO NOVO)'
        )
        codes = sorted(int(m['nameShort']) for m in group.members)
        self.assertEqual(codes, [1268, 1270])
        self.assertNotIn(group, self.result.flagged)
        self.assertLess(group.span_m, 75)

    def test_every_member_keeps_its_own_code(self):
        """The pole code is what a user standing at a stop can actually read."""
        for group in self.result.groups:
            codes = [m['nameShort'] for m in group.members]
            self.assertEqual(len(codes), len(set(codes)))
            self.assertTrue(all(codes))


class DeterminismTests(SimpleTestCase):
    def test_collapse_is_stable_across_input_order(self):
        stops = upstream_stops()
        first = collapse_stops(stops)
        second = collapse_stops(list(reversed(stops)))

        self.assertEqual(
            [g.name for g in first.groups], [g.name for g in second.groups],
        )
        self.assertEqual(
            [round(g.latitude, 9) for g in first.groups],
            [round(g.latitude, 9) for g in second.groups],
        )
