"""A product's seed must carry that product's islands and nothing else.

The Madeira app ships a seed built from the same atlas as the Azores app; without a
filter it would bundle all nine Azores islands' POIs — megabytes of content for a
different product, and Azores rows visible in a Madeira-only app.
"""
import sqlite3
import tempfile
from pathlib import Path

from django.test import TestCase

from atlas.models import AtlasCategory, AtlasPoi, AtlasRevision
from atlas.seed_db import build_seed_db
from tenancy.models import Island


class SeedDbIslandFilterTests(TestCase):
    def setUp(self):
        for key in ('sao-miguel', 'madeira', 'porto-santo'):
            island = Island.objects.get(key=key)
            AtlasRevision.objects.get_or_create(island=island)
            category, _ = AtlasCategory.objects.get_or_create(
                island=island, slug='viewpoints',
                defaults={'name': {'pt': 'Miradouros', 'en': 'Viewpoints'}, 'is_active': True})
            AtlasPoi.objects.create(
                island=island, category=category, source=AtlasPoi.SOURCE_OSM,
                source_ref=f'node/{key}', name={'pt': key, 'en': key},
                latitude=island.center_lat, longitude=island.center_lng,
                is_published=True, is_active=True)

    def _build(self, **kwargs):
        path = Path(tempfile.mkdtemp()) / 'atlas-seed.db'
        counts = build_seed_db(path, **kwargs)
        connection = sqlite3.connect(path)
        self.addCleanup(connection.close)
        return connection, counts

    def test_filtered_seed_contains_only_the_requested_islands(self):
        connection, _ = self._build(island_keys=['madeira', 'porto-santo'])
        for table in ('poi', 'trail', 'category', 'sync_state'):
            islands = {row[0] for row in connection.execute(f'SELECT DISTINCT island FROM {table}')}
            self.assertLessEqual(islands, {'madeira', 'porto-santo'}, table)

    def test_unfiltered_seed_is_unchanged(self):
        connection, counts = self._build()
        islands = {row[0] for row in connection.execute('SELECT DISTINCT island FROM sync_state')}
        self.assertIn('sao-miguel', islands)
        self.assertEqual(counts['islands'], len(islands))

    def test_unknown_island_key_is_rejected(self):
        with self.assertRaises(ValueError):
            self._build(island_keys=['atlantis'])


class SeedDbTrailExclusionTests(SeedDbIslandFilterTests):
    """Trails ship in the release pack, not the seed.

    A seeded trail arrives with a real revision, and prepareTrailBundle only attaches the
    bundled GPX to rows at revision 0 — so a trail in the seed silently ends up with no
    offline track, which is the whole point of the product.
    """

    def _trail(self, island_key):
        from atlas.models import AtlasTrail
        island = Island.objects.get(key=island_key)
        return AtlasTrail.objects.create(
            island=island, source=AtlasTrail.SOURCE_TRAILS, source_ref='PR1',
            name={'pt': 'Vereda', 'en': 'Vereda'}, is_published=True, is_active=True,
            geojson={'type': 'LineString', 'coordinates': [[-16.9, 32.7], [-16.91, 32.71]]})

    def test_without_trails_omits_trail_rows_but_keeps_pois(self):
        self._trail('madeira')
        connection, counts = self._build(island_keys=['madeira'], include_trails=False)
        self.assertEqual(counts['trails'], 0)
        self.assertEqual(connection.execute('SELECT COUNT(*) FROM trail').fetchone()[0], 0)
        self.assertGreater(connection.execute('SELECT COUNT(*) FROM poi').fetchone()[0], 0)

    def test_trails_are_included_by_default(self):
        self._trail('madeira')
        _, counts = self._build(island_keys=['madeira'])
        self.assertEqual(counts['trails'], 1)
