"""Which Madeira area an OSM element belongs to.

Nearest-island-centre is the Azores rule, and it breaks here: Ponta de São Lourenço and
its islets sit at Madeira's eastern tip but are closer to the Desertas centre than to
Madeira's, so they would import under an uninhabited nature reserve.
"""
import json
from pathlib import Path

from django.test import TestCase

from atlas.importers.osm import OsmImporter
from tenancy.models import Island

# Ilhéu do Farol, the outermost islet of Ponta de São Lourenço (Madeira).
FAROL_LAT, FAROL_LON = 32.7350, -16.6550
# Deserta Grande, the main Desertas island.
DESERTA_LAT, DESERTA_LON = 32.5100, -16.5100


class MadeiraAreaOwnershipTests(TestCase):
    def setUp(self):
        self.madeira = Island.objects.get(key='madeira')
        self.desertas = Island.objects.get(key='desertas')

    def _write_extract(self, island, elements):
        path = OsmImporter(island).extract_path()
        path.write_text(json.dumps(elements), encoding='utf-8')
        self.addCleanup(lambda: path.exists() and path.unlink())
        return path

    def test_ponta_de_sao_lourenco_belongs_to_madeira_not_desertas(self):
        self.assertTrue(OsmImporter(self.madeira)._owns(FAROL_LAT, FAROL_LON))
        self.assertFalse(OsmImporter(self.desertas)._owns(FAROL_LAT, FAROL_LON))

    def test_deserta_grande_belongs_to_desertas(self):
        self.assertTrue(OsmImporter(self.desertas)._owns(DESERTA_LAT, DESERTA_LON))
        self.assertFalse(OsmImporter(self.madeira)._owns(DESERTA_LAT, DESERTA_LON))

    def test_azores_islands_keep_nearest_centre_ownership(self):
        sao_miguel = Island.objects.get(key='sao-miguel')
        self.assertTrue(OsmImporter(sao_miguel)._owns(sao_miguel.center_lat, sao_miguel.center_lng))
        self.assertFalse(OsmImporter(sao_miguel)._owns(FAROL_LAT, FAROL_LON))

    def test_element_outside_every_madeira_area_is_dropped(self):
        # Mid-Atlantic, between the two archipelagos.
        self.assertFalse(OsmImporter(self.madeira)._owns(34.5, -20.0))
        self.assertFalse(OsmImporter(self.desertas)._owns(34.5, -20.0))
