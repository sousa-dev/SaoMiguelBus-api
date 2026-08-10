"""A monthly OSM re-import must not erase AI-enriched content on a row it re-touches
(SDD 02 §5.2.3, 04 risk table). This is the same failure shape as the editorial-overwrite bug
the import-ownership rule prevents, just with `enrich_atlas_pois` in the victim role."""

from __future__ import annotations

from django.test import TestCase

from atlas.importers.base import BaseImporter, ImportRow
from atlas.models import AtlasCategory, AtlasPoi
from tenancy.services import get_or_create_default_island


class _FakeOsmImporter(BaseImporter):
    SOURCE = AtlasPoi.SOURCE_OSM

    def __init__(self, island, rows):
        super().__init__(island)
        self._rows = rows

    def rows(self):
        return iter(self._rows)


class EnrichmentMergeSafetyTestCase(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        self.category = AtlasCategory.objects.create(
            island=self.island, slug='test-merge-cat', name={'en': 'Test'},
        )
        self.row = ImportRow(
            ref='osm-merge-1', name={'en': 'Original name'},
            latitude=37.8, longitude=-25.5, category_slug='test-merge-cat',
        )

    def test_reimport_preserves_enriched_fields(self):
        _FakeOsmImporter(self.island, [self.row]).run()
        poi = AtlasPoi.objects.get(island=self.island, source=AtlasPoi.SOURCE_OSM, source_ref='osm-merge-1')

        # Simulate enrich_atlas_pois having already enriched this row.
        poi.tier = AtlasPoi.TIER_ENRICHED
        poi.description = {'en': 'A carefully written description.'}
        poi.tips = {'en': ['Go early.']}
        poi.save(update_fields=['tier', 'description', 'tips'])

        # Monthly re-import runs again with the same upstream row (e.g. only the raw OSM
        # `name` tag changed slightly).
        updated_row = ImportRow(
            ref='osm-merge-1', name={'en': 'Original name (updated)'},
            latitude=37.8, longitude=-25.5, category_slug='test-merge-cat',
        )
        _FakeOsmImporter(self.island, [updated_row]).run()

        poi.refresh_from_db()
        self.assertEqual(poi.name['en'], 'Original name (updated)', 'importer should refresh its own fields')
        self.assertEqual(poi.tier, AtlasPoi.TIER_ENRICHED, 're-import must not revert enrichment tier')
        self.assertEqual(poi.description['en'], 'A carefully written description.')
        self.assertEqual(poi.tips['en'], ['Go early.'])
