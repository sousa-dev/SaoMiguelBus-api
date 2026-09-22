from unittest.mock import patch
from django.test import TestCase
from atlas.importers.curated import CuratedImporter
from atlas.importers.osm import OsmImporter
from atlas.models import AtlasCategory, AtlasPoi
from tenancy.services import get_or_create_default_island


class MissingInputDoesNotDeleteContentTests(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        self.category = AtlasCategory.objects.create(island=self.island, slug='places', name={'en': 'Places'})

    def test_missing_osm_extract_preserves_existing_poi(self):
        poi = AtlasPoi.objects.create(island=self.island, category=self.category,
                                      source=AtlasPoi.SOURCE_OSM, source_ref='node/1',
                                      name={'en': 'Existing'}, latitude=37.8, longitude=-25.5,
                                      is_active=True, is_published=True)
        with patch.object(OsmImporter, 'extract_path', return_value=__import__('pathlib').Path('/tmp/nonexistent-madeira-osm.json')):
            OsmImporter(self.island).run()
        poi.refresh_from_db()
        self.assertTrue(poi.is_active)

    def test_missing_curated_extract_preserves_existing_poi(self):
        poi = AtlasPoi.objects.create(island=self.island, category=self.category,
                                      source=AtlasPoi.SOURCE_CURATED, source_ref='place-1',
                                      name={'en': 'Existing'}, latitude=37.8, longitude=-25.5,
                                      is_active=True, is_published=True)
        with patch.object(CuratedImporter, 'data_path', return_value=__import__('pathlib').Path('/tmp/nonexistent-madeira-curated.json')):
            CuratedImporter(self.island).run()
        poi.refresh_from_db()
        self.assertTrue(poi.is_active)
