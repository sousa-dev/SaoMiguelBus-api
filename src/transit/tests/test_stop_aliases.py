"""Old stop names must keep resolving after canonicalization renames them.

Canonicalization rewrites 437 of the 814 AzoresBus stop names, and
`cleaned_name` is what every lookup in this codebase resolves against. Without
`StopAlias`, the day the rename ships: every favourite starred in the app
stops resolving, every deep link shared in a message 404s, and typing
"S. Roque" -- the spelling printed on the pole -- finds nothing.

The alias branch sits ABOVE the village-area branch on purpose. An alias names
exactly one stop, so widening a precise old link into a whole village would
give the user results they never asked for.
"""

from __future__ import annotations

from django.test import TestCase

from azoresbus.services_stops import build_azoresbus_area_index
from tenancy.services import get_or_create_default_island
from transit.models import DATASET_AZORESBUS, Stop, StopAlias
from transit.services.search import resolve_stop_by_name, resolve_stop_ids


class AliasFixture(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        self.stops = {}
        for name, lat, lon in [
            ('Ponta Delgada (Marina)', 37.7394, -25.6690),
            ('Ponta Delgada (Hospital)', 37.7500, -25.6700),
            ('Ponta Delgada (Alfândega)', 37.7384, -25.6692),
            ('São Roque (Igreja)', 37.7505, -25.6300),
            ('Achadinha', 37.8400, -25.2000),
        ]:
            self.stops[name] = Stop.objects.create(
                island=self.island, dataset=DATASET_AZORESBUS, name=name,
                cleaned_name=name.lower()
                .replace('â', 'a').replace('ã', 'a').replace('á', 'a')
                .replace('é', 'e').replace('ó', 'o').replace('ç', 'c'),
                latitude=lat, longitude=lon,
            )

    def alias(self, cleaned_alias: str, stop_name: str) -> StopAlias:
        return StopAlias.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS,
            cleaned_alias=cleaned_alias, stop=self.stops[stop_name],
        )


class ResolveStopIdsAliasTests(AliasFixture):
    def test_a_retired_name_resolves_to_the_renamed_stop(self):
        self.alias('p. delgada (marina)', 'Ponta Delgada (Marina)')
        self.assertEqual(
            resolve_stop_ids(DATASET_AZORESBUS, 'p. delgada (marina)', None),
            {self.stops['Ponta Delgada (Marina)'].id},
        )

    def test_an_exact_current_name_still_wins_over_an_alias(self):
        """An alias must never be able to hijack a real stop's own name."""
        self.alias('achadinha', 'Ponta Delgada (Marina)')
        self.assertEqual(
            resolve_stop_ids(DATASET_AZORESBUS, 'achadinha', None),
            {self.stops['Achadinha'].id},
        )

    def test_an_unknown_name_still_falls_through_to_the_prefix_fallback(self):
        self.assertEqual(
            resolve_stop_ids(DATASET_AZORESBUS, 'ponta delgada (h', None),
            {self.stops['Ponta Delgada (Hospital)'].id},
        )

    def test_an_alias_beats_the_prefix_fallback(self):
        """"p. delgada (marina)" has no prefix match, but must not be lost."""
        self.alias('p. delgada (marina)', 'Ponta Delgada (Marina)')
        ids = resolve_stop_ids(DATASET_AZORESBUS, 'p. delgada (marina)', None)
        self.assertEqual(ids, {self.stops['Ponta Delgada (Marina)'].id})


class ResolveStopByNameTests(AliasFixture):
    """The helper behind directions, gmaps and route-weather.

    All three used raw `name__iexact` before, which breaks the moment a client
    sends a name the stop no longer has -- and was accent-sensitive besides.
    """

    def test_current_name(self):
        stop = resolve_stop_by_name(DATASET_AZORESBUS, 'Ponta Delgada (Marina)')
        self.assertEqual(stop, self.stops['Ponta Delgada (Marina)'])

    def test_retired_name(self):
        self.alias('p. delgada (marina)', 'Ponta Delgada (Marina)')
        stop = resolve_stop_by_name(DATASET_AZORESBUS, 'P. DELGADA (MARINA)')
        self.assertEqual(stop, self.stops['Ponta Delgada (Marina)'])

    def test_accent_insensitive_where_iexact_was_not(self):
        stop = resolve_stop_by_name(DATASET_AZORESBUS, 'ponta delgada (alfandega)')
        self.assertEqual(stop, self.stops['Ponta Delgada (Alfândega)'])

    def test_unknown_name_is_none(self):
        self.assertIsNone(resolve_stop_by_name(DATASET_AZORESBUS, 'Nowhere'))


class AreaAliasTests(AliasFixture):
    """A retired VILLAGE prefix must still open the whole village."""

    def test_retired_village_prefix_opens_the_canonical_village(self):
        self.alias('p. delgada (marina)', 'Ponta Delgada (Marina)')
        self.alias('p. delgada (hospital)', 'Ponta Delgada (Hospital)')
        index = build_azoresbus_area_index(DATASET_AZORESBUS)

        self.assertIn('ponta delgada', index)
        self.assertIn('p. delgada', index)
        self.assertEqual(index['p. delgada'], index['ponta delgada'])
        self.assertEqual(len(index['ponta delgada']), 3)

    def test_an_ambiguous_old_prefix_is_dropped_not_guessed(self):
        """"sta. barbara" named two villages. Half those users would land in
        the wrong one, which is worse than falling through."""
        for name, lat in [('Santa Bárbara (Escolas)', 37.8733),
                          ('Santa Bárbara (Rua Couto)', 37.8696),
                          ('Santa Bárbara da Ribeira Grande (Areal)', 37.8006),
                          ('Santa Bárbara da Ribeira Grande (Meio)', 37.7960)]:
            self.stops[name] = Stop.objects.create(
                island=self.island, dataset=DATASET_AZORESBUS, name=name,
                cleaned_name=name.lower().replace('á', 'a').replace('ã', 'a'),
                latitude=lat, longitude=-25.6,
            )
        self.alias('sta. barbara (escolas)', 'Santa Bárbara (Escolas)')
        self.alias('sta. barbara (areal)',
                   'Santa Bárbara da Ribeira Grande (Areal)')

        index = build_azoresbus_area_index(DATASET_AZORESBUS)
        self.assertIn('santa barbara', index)
        self.assertIn('santa barbara da ribeira grande', index)
        self.assertNotIn('sta. barbara', index)

    def test_an_alias_never_shadows_a_string_a_real_stop_answers_to(self):
        """`São Roque (Igreja)` is the only São Roque, so "sao roque" is not an
        area key -- but it still resolves to that stop via the prefix
        fallback. An alias must not be able to redirect it to another village.
        """
        self.alias('sao roque (igreja)', 'Ponta Delgada (Marina)')
        index = build_azoresbus_area_index(DATASET_AZORESBUS)
        self.assertNotIn('sao roque', index)
        self.assertEqual(
            resolve_stop_ids(DATASET_AZORESBUS, 'sao roque', index),
            {self.stops['São Roque (Igreja)'].id},
        )

    def test_an_alias_never_overwrites_an_existing_area_key(self):
        self.alias('ponta delgada (marina)', 'Achadinha')
        index = build_azoresbus_area_index(DATASET_AZORESBUS)
        self.assertNotIn(self.stops['Achadinha'].id, index['ponta delgada'])
