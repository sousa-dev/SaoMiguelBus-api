"""Visit Azores trails sync tests."""

from unittest.mock import patch

from django.test import TestCase

from trails.visitazores_sync import (
    gpx_to_linestring,
    parse_trail_detail_page,
    sync_visitazores_trails_for_island,
)
from tenancy.services import get_or_create_default_island

SAMPLE_DETAIL_HTML = """
<html><head>
<meta property="og:title" content="Caldeiras da Ribeira Grande - Salto do Cabrito | Azores Trails" />
<script>jQuery.extend(Drupal.settings, {"geofieldMap":{"map":{"data":{"type":"LineString","coordinates":[[-25.50,37.78],[-25.49,37.79]],"properties":{"description":"Caldeiras"}}}}});</script>
</head><body>
<div class="field field-name-field-difficulty"><div class="field-item even">Difficulty - Medium</div></div>
<div class="field field-name-field-extension"><div class="field-item even">Extension - 8.6 km</div></div>
PRC29SMI
<a href="https://trails.visitazores.com/sites/default/files/trails/sao-miguel/prc29smi.gpx">GPS</a>
</body></html>
"""

SAMPLE_GPX = """<?xml version="1.0"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1">
<trk><trkseg>
<trkpt lat="37.78" lon="-25.50"/>
<trkpt lat="37.79" lon="-25.49"/>
</trkseg></trk>
</gpx>"""


class VisitAzoresSyncTestCase(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        self.island.feature_flags = {**self.island.feature_flags, 'trails': True}
        self.island.save()

    def test_parse_trail_detail_page_extracts_fields(self):
        row = parse_trail_detail_page(SAMPLE_DETAIL_HTML, page_url='https://example.test/trail')
        assert row is not None
        self.assertEqual(row['source_ref'], 'PRC29SMI')
        self.assertEqual(row['name'], 'Caldeiras da Ribeira Grande - Salto do Cabrito')
        self.assertEqual(row['difficulty'], 'moderate')
        self.assertEqual(row['distance_km'], 8.6)
        self.assertEqual(row['geojson']['type'], 'LineString')

    def test_gpx_to_linestring(self):
        geometry = gpx_to_linestring(SAMPLE_GPX)
        assert geometry is not None
        self.assertEqual(geometry['coordinates'][0], [-25.50, 37.78])

    @patch('trails.visitazores_sync.fetch_feed_trail_summaries', return_value={})
    @patch('trails.visitazores_sync.fetch_island_trail_paths', return_value=['/en/trails-azores/sao-miguel/test'])
    @patch('trails.visitazores_sync._get_html', return_value=SAMPLE_DETAIL_HTML)
    def test_sync_visitazores_trails_for_island(self, *_mocks):
        counts = sync_visitazores_trails_for_island(self.island)
        self.assertEqual(counts['created'], 1)
        self.assertEqual(counts['skipped'], 0)
