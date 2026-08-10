"""TrailsImporter regressions — deterministic UUIDs + idempotent upserts.

The Offline Map release bundler assigns the same UUIDv5 (see atlas.identifiers) so a
fresh install's seeded trails and a later Atlas sync converge on one row per source_ref.
"""

from __future__ import annotations

from django.test import TestCase

from atlas.identifiers import ATLAS_UID_NAMESPACE, atlas_trail_uid
from atlas.importers.trails import TrailsImporter
from atlas.models import AtlasTrail, AtlasTrailStage
from tenancy.services import get_or_create_default_island
from trails.models import Trail, TrailStage


class AtlasTrailUidTestCase(TestCase):
    def test_known_vector_matches_python_uuid5(self):
        import uuid

        expected = uuid.uuid5(ATLAS_UID_NAMESPACE, 'trail:sao-miguel:PR12SMI')
        self.assertEqual(atlas_trail_uid('sao-miguel', 'PR12SMI'), expected)
        # Stable fixture shared with Azores-OfflineMap/build/trails/bundle.test.mjs
        self.assertEqual(str(expected), 'd79faaea-944d-5cde-8252-3466156eac3c')

    def test_requires_island_and_ref(self):
        with self.assertRaises(ValueError):
            atlas_trail_uid('', 'PR12SMI')
        with self.assertRaises(ValueError):
            atlas_trail_uid('sao-miguel', '')


class TrailsImporterTestCase(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island('sao-miguel')
        self.source = Trail.objects.create(
            island=self.island,
            source_ref='PR12SMI',
            name='Agrião',
            difficulty='moderate',
            distance_km=7.1,
            shape='linear',
            duration_min=180,
            description_pt='Descrição',
            description_en='Description',
            gpx_url='https://example.com/pr12.gpx',
            kml_url='https://example.com/pr12.kml',
            map_image_url='https://example.com/pr12.jpg',
            leaflet_url='https://example.com/pr12.pdf',
            start_lat=37.7469,
            start_lon=-25.2485,
            waypoints=[],
            geojson={
                'type': 'LineString',
                'coordinates': [[-25.2485, 37.7469], [-25.24, 37.75]],
            },
        )
        TrailStage.objects.create(
            island=self.island,
            trail=self.source,
            name='Stage 1',
            sequence=1,
            geojson={'type': 'LineString', 'coordinates': [[-25.2485, 37.7469], [-25.24, 37.75]]},
        )

    def test_create_assigns_deterministic_uid(self):
        result = TrailsImporter(self.island).run()
        self.assertEqual(result['trails_created'], 1)
        trail = AtlasTrail.objects.get(source=AtlasTrail.SOURCE_TRAILS, source_ref='PR12SMI')
        self.assertEqual(trail.uid, atlas_trail_uid('sao-miguel', 'PR12SMI'))
        self.assertTrue(trail.is_published)
        self.assertEqual(AtlasTrailStage.objects.filter(trail=trail).count(), 1)

    def test_reimport_is_idempotent_and_preserves_uid(self):
        TrailsImporter(self.island).run()
        first = AtlasTrail.objects.get(source_ref='PR12SMI')
        first_uid = first.uid
        first_revision = first.revision

        self.source.name = 'Agrião (updated)'
        self.source.save(update_fields=['name'])
        result = TrailsImporter(self.island).run()

        self.assertEqual(result['trails_created'], 0)
        self.assertEqual(result['trails_updated'], 1)
        second = AtlasTrail.objects.get(source_ref='PR12SMI')
        self.assertEqual(second.uid, first_uid)
        self.assertEqual(second.name.get('pt'), 'Agrião (updated)')
        self.assertGreater(second.revision, first_revision)
        self.assertEqual(AtlasTrail.objects.filter(source_ref='PR12SMI').count(), 1)
