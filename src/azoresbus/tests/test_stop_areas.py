"""Village-level ("area") search grouping — a DIFFERENT concept from the
pole-collapse in `test_stop_collapse.py`.

Pole-collapse (`collapse_stops`) merges 1456 physical poles into 816 `Stop` rows
by EXACT name, at import time — both sides of a road sharing one name. This
groups those already-collapsed 816 names by a shared VILLAGE PREFIX, at search
time: "CAPELAS (IGREJA)", "CAPELAS (MOAGEM)" etc share the key "CAPELAS" so a
search for "Capelas" can union every stop in the village. Different axis,
different purpose — do not conflate the two.

Driven by the same real /api/stops payload as the pole-collapse tests, reduced
to the post-collapse name set (no new fixture needed).
"""

from __future__ import annotations

import json
from pathlib import Path

from django.test import SimpleTestCase

from azoresbus.services_stops import (
    build_area_index,
    collapse_stops,
    derive_area_key,
)
from transit.services.legacy_import import clean_string


FIXTURES = Path(__file__).parent / 'fixtures'


def real_stop_names() -> list[str]:
    """The 814 real, distinct AzoresBus stop names as STORED.

    Goes through `collapse_stops` rather than reading `row['name']` directly,
    because that is what `Stop.name` actually holds: canonicalized, not
    verbatim upstream. Reading the raw fixture instead would keep these
    assertions green while testing a name domain production no longer uses --
    they would still pin 83 areas while the API served 79.
    """
    return sorted(group.name for group in collapse_stops(upstream_stops()).groups)


def upstream_stops() -> list[dict]:
    return json.loads((FIXTURES / 'stops.json').read_text(encoding='utf-8'))


class FakeStop:
    """Bare stand-in for `transit.models.Stop` — area grouping only reads
    `.id`/`.name`, so a Django-model-free fixture keeps these tests a
    `SimpleTestCase` with no database."""

    _next_id = 1

    def __init__(self, name: str):
        self.id = FakeStop._next_id
        FakeStop._next_id += 1
        self.name = name


def fake_stops(names: list[str]) -> list[FakeStop]:
    return [FakeStop(name) for name in names]


class DeriveAreaKeyTests(SimpleTestCase):
    def test_splits_on_the_first_open_paren(self):
        self.assertEqual(derive_area_key('CAPELAS (IGREJA)'), 'CAPELAS')

    def test_a_bare_name_with_no_parens_has_no_area(self):
        self.assertIsNone(derive_area_key('ACHADINHA'))

    def test_a_trailing_pole_number_after_the_paren_still_groups(self):
        """ARRIFES (LG. DO BOM DESPACHO) 1 / 2 -- splitting on the FIRST '('
        rather than requiring the string to end in ')' is what catches this."""
        self.assertEqual(
            derive_area_key('ARRIFES (LG. DO BOM DESPACHO) 1'), 'ARRIFES',
        )
        self.assertEqual(
            derive_area_key('ARRIFES (LG. DO BOM DESPACHO) 2'), 'ARRIFES',
        )

    def test_trims_whitespace_before_the_paren(self):
        self.assertEqual(derive_area_key('CAPELAS  (IGREJA)'), 'CAPELAS')


class BuildAreaIndexRealDataTests(SimpleTestCase):
    """Pinned against the real, committed upstream fixture — 98-style regression
    anchors, not hand-typed examples."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        FakeStop._next_id = 1
        cls.names = real_stop_names()
        cls.stops = fake_stops(cls.names)
        cls.index = build_area_index(cls.stops)

    def test_real_area_count_and_coverage(self):
        self.assertEqual(len(self.names), 814)
        self.assertEqual(len(self.index), 79)
        covered = sum(len(ids) for ids in self.index.values())
        self.assertEqual(covered, 778)

    def test_capelas_has_37_members(self):
        key = 'capelas'  # folded -- see test_area_index_keys_are_folded
        self.assertIn(key, self.index)
        self.assertEqual(len(self.index[key]), 37)

    def test_spelling_variants_no_longer_split_a_village(self):
        """The whole point: one village, one area key.

        Before canonicalization `P. DELGADA` and `PONTA DELGADA` were separate
        keys, so "Ponta Delgada" resolved to 3 stops out of 38. `SÃO VICENTE
        FERREIRA` was worse -- 29 stops and NO key at all, because each of its
        two spellings looked like a sub-2-member singleton to the rule below.
        """
        self.assertEqual(len(self.index['ponta delgada']), 38)
        self.assertEqual(len(self.index['sao vicente ferreira']), 29)
        self.assertEqual(len(self.index['sao roque']), 17)
        self.assertEqual(len(self.index['vila do nordeste']), 12)
        for retired in ('p. delgada', 'v. do nordeste', 's. roque', 'nordeste'):
            self.assertNotIn(retired, self.index)

    def test_numbered_variants_rejoin_their_village(self):
        """`LOMBA DO BOTÃO 1/2/3` were three 1-member keys, so all three were
        dropped. Parenthesising the discriminator puts them back in the
        village without merging them into one stop."""
        self.assertEqual(len(self.index['lomba do botao']), 9)

    def test_the_two_santa_barbaras_stay_apart(self):
        """A blind `STA. -> Santa` rewrite would union two villages 16.5 km
        apart. The code-scoped override keeps them as separate areas."""
        self.assertIn('santa barbara', self.index)
        self.assertIn('santa barbara da ribeira grande', self.index)
        self.assertEqual(len(self.index['santa barbara da ribeira grande']), 11)

    def test_largest_area_is_arrifes_with_47(self):
        largest_key = max(self.index, key=lambda k: len(self.index[k]))
        self.assertEqual(largest_key, 'arrifes')
        self.assertEqual(len(self.index['arrifes']), 47)

    def test_single_member_areas_are_excluded(self):
        """17 keys have exactly one parenthetical member -- no grouping benefit."""
        # A single-member key would have to come from a name that has no sibling
        # sharing its prefix; none of those appear as index keys.
        singleton_examples = ['achadinha (burguete)', 'algarvia (pico da vara)']
        for name in singleton_examples:
            key = derive_area_key(name.upper())
            self.assertIsNotNone(key)
            self.assertNotIn(key.lower(), self.index)

    def test_collision_excluded_areas_are_absent(self):
        """AFLITOS, VÁRZEA, ACHADINHA, ALGARVIA, RIBEIRA FUNDA all collide with a
        real bare stop of that exact name -- excluded so the string "Aflitos"
        keeps meaning exactly one thing (98-style: only apply where it works).
        Checked in FOLDED form, since that's the domain the index actually
        keys on -- the raw accented string is never a key either way, so
        asserting against it would pass trivially and prove nothing."""
        for excluded in ('aflitos', 'varzea', 'achadinha', 'algarvia', 'ribeira funda'):
            self.assertNotIn(excluded, self.index)

    def test_area_index_keys_are_folded(self):
        """The lookup side (`resolve_stop_ids`) folds the query via
        `clean_string`, exactly like every other Stop lookup in this codebase.
        If the index kept RAW keys, 'capelas' would never match 'CAPELAS' -- a
        dict lookup is exact, not case/accent-insensitive."""
        self.assertIn('capelas', self.index)
        self.assertNotIn('CAPELAS', self.index)
        self.assertNotIn('Capelas', self.index)

    def test_every_member_id_is_a_real_stop_in_the_area(self):
        """Same fold as production (`clean_string`), not a plain .lower() --
        several real area keys contain accents (e.g. FAJÃ DE BAIXO, PONTA
        GARÇA), which .lower() alone would not fold to match the index key."""
        by_id = {stop.id: stop.name for stop in self.stops}
        for key, member_ids in self.index.items():
            for stop_id in member_ids:
                raw_key = derive_area_key(by_id[stop_id])
                self.assertIsNotNone(raw_key)
                self.assertEqual(
                    clean_string(raw_key), key,
                    f'stop {by_id[stop_id]!r} does not belong under {key!r}',
                )


class CollisionExclusionTests(SimpleTestCase):
    """Small, hand-built fixtures -- isolates the exclusion rule from the real
    dataset's incidental size."""

    def test_a_bare_stop_blocks_its_own_area_key(self):
        stops = fake_stops(['AFLITOS', 'AFLITOS (ESCOLA)', 'AFLITOS (IGREJA)'])
        index = build_area_index(stops)
        self.assertNotIn('aflitos', index)

    def test_the_exclusion_is_accent_and_case_folded(self):
        stops = fake_stops(['Água Retorta', 'AGUA RETORTA (PORTO)', 'AGUA RETORTA (PRAIA)'])
        index = build_area_index(stops)
        self.assertNotIn('agua retorta', index)

    def test_without_a_colliding_bare_stop_the_area_forms_normally(self):
        stops = fake_stops(['CAPELAS (IGREJA)', 'CAPELAS (MOAGEM)'])
        index = build_area_index(stops)
        self.assertIn('capelas', index)
        self.assertEqual(len(index['capelas']), 2)

    def test_a_single_matching_stop_never_forms_an_area(self):
        stops = fake_stops(['CAPELAS (IGREJA)', 'ARRIFES (ESCOLA)'])
        index = build_area_index(stops)
        self.assertEqual(index, {})

    def test_two_different_raw_keys_that_fold_together_are_merged(self):
        """Would only happen with an accent/case variant of the same village
        name across two source rows; the index must not silently split them."""
        stops = fake_stops(['SÃO ROQUE (IGREJA)', 'SAO ROQUE (ESCOLA)'])
        index = build_area_index(stops)
        self.assertIn('sao roque', index)
        self.assertEqual(len(index['sao roque']), 2)


class DeterminismTests(SimpleTestCase):
    def test_index_is_stable_across_input_order(self):
        names = real_stop_names()
        first = build_area_index(fake_stops(names))
        FakeStop._next_id = 1
        second = build_area_index(fake_stops(list(reversed(names))))
        self.assertEqual(set(first), set(second))
        self.assertEqual(
            {k: len(v) for k, v in first.items()},
            {k: len(v) for k, v in second.items()},
        )
