"""Post-migration state of the nine seeded islands.

These assert the *outcome* of the seed/flag migration chain rather than any one migration,
because the bug they guard was an ordering bug: 0007_enable_trails_feature_flag filters
key='sao-miguel' and no-ops on a fresh database (the row does not exist yet), then
0018_seed_sao_miguel_island creates that row with trails: False — so every new deploy came up
with Hub's own nightly trails sync silently disabled. 0020 repairs it.
"""

from django.test import TestCase

from tenancy.models import Island
from trails.visitazores_sync import VISITAZORES_ISLAND_SLUGS

NINE_ISLANDS = {
    'sao-miguel',
    'santa-maria',
    'terceira',
    'graciosa',
    'sao-jorge',
    'pico',
    'faial',
    'flores',
    'corvo',
}


class IslandSeedStateTestCase(TestCase):
    def test_all_nine_islands_are_seeded_and_live(self):
        islands = {i.key: i for i in Island.objects.all()}
        self.assertEqual(NINE_ISLANDS - set(islands), set())
        for key in NINE_ISLANDS:
            with self.subTest(island=key):
                self.assertTrue(islands[key].is_live)

    def test_trails_flag_enabled_everywhere(self):
        """_islands_for_sync() filters on this flag — without it the nightly sync skips the
        island entirely, which is why the other eight never had trails."""
        for island in Island.objects.filter(key__in=NINE_ISLANDS):
            with self.subTest(island=island.key):
                self.assertTrue((island.feature_flags or {}).get('trails'))

    def test_atlas_flag_enabled_everywhere(self):
        # atlas.import_all_sources filters on this; it is what carries trails through to the
        # offline map app's delta sync.
        for island in Island.objects.filter(key__in=NINE_ISLANDS):
            with self.subTest(island=island.key):
                self.assertTrue((island.feature_flags or {}).get('atlas'))

    def test_radii_cover_measured_trail_extents(self):
        """Minimum radius_km needed for every official trail on the island to have at least
        one coordinate inside island_bbox(), measured from the live Visit Azores geometry."""
        measured_need_km = {
            'sao-miguel': 31.3,
            'santa-maria': 13.9,
            'terceira': 12.8,
            'graciosa': 8.3,
            'sao-jorge': 19.4,
            'pico': 32.2,
            'faial': 11.1,
            'flores': 11.4,
            'corvo': 4.9,
        }
        for island in Island.objects.filter(key__in=measured_need_km):
            with self.subTest(island=island.key):
                self.assertGreaterEqual(island.radius_km, measured_need_km[island.key])

    def test_every_island_has_a_visitazores_slug(self):
        self.assertEqual(NINE_ISLANDS, set(VISITAZORES_ISLAND_SLUGS))
