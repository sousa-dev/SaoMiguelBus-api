"""1456 upstream stops collapse to 814 transit.Stop rows.

The duplicates are the two sides of a road: median 11.5 m apart, 629 of 630
pairs with consecutive integer codes. A tourist cannot choose a pole before
choosing a destination, so pickers get one row per name and the physical pole
comes back with the result instead (02 §3.2).

Which pole a trip serves is a property of its direction — of route 101's 27
names served both ways, 24 use a different code per direction — so it is kept on
ExternalStop rather than thrown away.

Names are canonicalized before grouping (see `services_names`), which is why
this is 814 and not the 816 raw distinct names: `S. ROQUE (BARRACUDA)` /
`SÃO ROQUE (BARRACUDA)` (15 m apart) and `P. DELGADA (AV. D. JOÃO III)` /
`P. DELGADA (AV. DOM JOÃO III)` (41 m, consecutive codes) are each one road
pair that upstream spells two ways, so exact-name grouping missed them.

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

    def test_1456_stops_become_814_groups(self):
        self.assertEqual(len(upstream_stops()), 1456)
        self.assertEqual(len(self.result.groups), 814)

    def test_raw_names_alone_would_leave_816(self):
        """The pole-collapse rule itself is unchanged; canonicalization is.

        Pinned separately so a future change to `services_names` cannot
        silently alter what exact-name grouping does.
        """
        self.assertEqual(len({s['name'] for s in upstream_stops()}), 816)

    def test_group_membership_matches_98(self):
        sizes = [len(group.members) for group in self.result.groups]
        self.assertEqual(sum(1 for n in sizes if n == 1), 177)
        self.assertEqual(sum(1 for n in sizes if n == 2), 632)
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
                'Covoada (Avenida 6 de Janeiro)',
                'Ponta Delgada (Alfândega)',
                'Ponta Delgada (Forte São Brás)',
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
            if g.name == 'Capelas (Largo Teatro Novo)'
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


class AmbiguityGuardTests(SimpleTestCase):
    """Expansion is what makes village search work, and what makes it dangerous.

    `STA. BÁRBARA` names two villages 16.5 km apart, and `S.` expands to
    São/Santo/Santa/Sete/Seca. Curated rules handle the collisions we know
    about; this guard is what catches the ones upstream has not invented yet.
    """

    @staticmethod
    def _pole(code: str, name: str, lat: float, lon: float) -> dict:
        return {
            'id': code,
            'name': name,
            'nameShort': code,
            'position': {'lat': lat, 'lon': lon},
        }

    def test_a_village_split_across_the_island_is_reported_and_unmerged(self):
        """Two spellings of one prefix, 20 km apart, with no curated rule.

        Merging them would union two unrelated villages behind one search
        term -- the exact failure the Santa Bárbara rule exists to prevent.
        """
        payload = [
            self._pole('9001', 'S. FICTÍCIA (IGREJA)', 37.74, -25.67),
            self._pole('9002', 'S. FICTÍCIA (ESCOLA)', 37.74, -25.68),
            self._pole('9003', 'SÃO FICTÍCIA (PORTO)', 37.82, -25.45),
        ]
        result = collapse_stops(payload)

        self.assertEqual(len(result.ambiguous_areas), 1)
        flag = result.ambiguous_areas[0]
        self.assertEqual(flag.name, 'São Fictícia')
        self.assertGreater(flag.span_m, 8_000)
        self.assertTrue(flag.unmerged)
        self.assertEqual(flag.raw_prefixes, ['S. FICTÍCIA', 'SÃO FICTÍCIA'])

        # Backed out: the abbreviated spelling keeps its own area rather than
        # being folded into the distant one.
        prefixes = {group.name.split(' (')[0] for group in result.groups}
        self.assertEqual(prefixes, {'S. Fictícia', 'São Fictícia'})

    def test_a_curated_merge_is_exempt_from_the_span_limit(self):
        """Vila do Nordeste spans 5.6 km on purpose -- it was approved.

        Without the exemption the guard would fight the curated table on
        every sync.
        """
        payload = [
            self._pole('6001', 'V. DO NORDESTE (TERMINAL)', 37.8319, -25.1455),
            self._pole('6056', 'NORDESTE (MIRAD. DA MADRUGADA)', 37.7887, -25.1466),
        ]
        result = collapse_stops(payload)
        self.assertEqual(result.ambiguous_areas, [])
        self.assertEqual(
            sorted(g.name for g in result.groups),
            ['Vila do Nordeste (Miradouro da Madrugada)',
             'Vila do Nordeste (Terminal)'],
        )

    def test_identical_upstream_prefixes_are_reported_but_left_alone(self):
        """`RIBEIRA SECA` is two villages 17.8 km apart TODAY, upstream's own
        spelling, and this change neither causes nor can fix it.

        Backing out a merge we did not make would mean inventing a
        distinction, which is a worse guess than leaving upstream's. Report
        it and let a human add a curated rule.
        """
        result = collapse_stops(upstream_stops())
        flags = {flag.name: flag for flag in result.ambiguous_areas}
        self.assertIn('Ribeira Seca', flags)
        self.assertFalse(flags['Ribeira Seca'].unmerged)
        self.assertEqual(flags['Ribeira Seca'].raw_prefixes, ['RIBEIRA SECA'])

    def test_the_real_payload_raises_no_other_ambiguity(self):
        """A new flag here means upstream added a collision -- go look."""
        result = collapse_stops(upstream_stops())
        self.assertEqual(
            [flag.name for flag in result.ambiguous_areas], ['Ribeira Seca'],
        )

    def test_no_abbreviation_survives_canonicalization(self):
        """A token here is one missing from the `services_names` tables."""
        self.assertEqual(collapse_stops(upstream_stops()).unexpanded, [])
