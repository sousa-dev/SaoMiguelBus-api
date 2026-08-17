"""Trails sync propagates into atlas on the same run.

Without this, AtlasTrail — the table the offline map app delta-syncs from — only ever caught
up when atlas.import_all_sources fired, which is beat-scheduled monthly (1st, 02:00 Azores).
A nightly trails sync, or a deploy-time one, stayed invisible to installed apps until then.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from atlas.models import AtlasTrail
from tenancy.models import Island
from trails.models import Trail
from trails.services import propagate_trails_to_atlas, sync_all_open_data

GEOJSON = {'type': 'LineString', 'coordinates': [[-28.7200, 38.5800], [-28.7100, 38.5850]]}


def _make_trail(island: Island, source_ref: str) -> Trail:
    return Trail.objects.create(
        island=island,
        source_ref=source_ref,
        name=f'Trail {source_ref}',
        difficulty='easy',
        distance_km=6.8,
        shape='circular',
        duration_min=150,
        start_lat=38.5800,
        start_lon=-28.7200,
        geojson=GEOJSON,
    )


class PropagateTrailsToAtlasTestCase(TestCase):
    def setUp(self):
        self.faial = Island.objects.get(key='faial')

    def test_creates_atlas_rows_for_synced_island(self):
        _make_trail(self.faial, 'PRC4FAI')

        imported = propagate_trails_to_atlas([self.faial])

        self.assertEqual(imported, 1)
        atlas_trail = AtlasTrail.objects.unscoped().get(island=self.faial, source_ref='PRC4FAI')
        self.assertTrue(atlas_trail.is_published)
        # A published row with a real revision is what build_sync_page() will actually send.
        self.assertGreater(atlas_trail.revision, 0)

    def test_skips_islands_without_the_atlas_flag(self):
        _make_trail(self.faial, 'PRC4FAI')
        self.faial.feature_flags = {**(self.faial.feature_flags or {}), 'atlas': False}
        self.faial.save(update_fields=['feature_flags'])

        self.assertEqual(propagate_trails_to_atlas([self.faial]), 0)
        self.assertFalse(AtlasTrail.objects.unscoped().filter(island=self.faial).exists())

    def test_importer_failure_is_contained(self):
        """The trails sync has already succeeded by this point — a downstream atlas problem
        must not surface as a failed trails sync."""
        _make_trail(self.faial, 'PRC4FAI')

        with patch(
            'atlas.importers.trails.TrailsImporter.run',
            side_effect=RuntimeError('boom'),
        ):
            self.assertEqual(propagate_trails_to_atlas([self.faial]), 0)

    def test_sync_all_open_data_propagates_only_islands_that_synced(self):
        ok, broken = self.faial, Island.objects.get(key='pico')
        _make_trail(ok, 'PRC4FAI')
        _make_trail(broken, 'PR9PIC')

        def fake_sync(island):
            if island.key == broken.key:
                raise ValueError('listing fetch failed')
            return {
                'trails_created': 1, 'trails_updated': 0,
                'pois_created': 0, 'pois_updated': 0, 'skipped': 0,
            }

        with patch('trails.services.sync_open_data_for_island', side_effect=fake_sync):
            with patch(
                'trails.services._islands_for_sync', return_value=[ok, broken],
            ):
                totals = sync_all_open_data()

        self.assertEqual(totals['failed_islands'], 1)
        self.assertEqual(totals['atlas_islands_imported'], 1)
        self.assertTrue(AtlasTrail.objects.unscoped().filter(island=ok).exists())
        # Pico's trails sync failed, so its pre-existing rows must not be republished from a
        # half-synced state on the back of another island's success.
        self.assertFalse(AtlasTrail.objects.unscoped().filter(island=broken).exists())
