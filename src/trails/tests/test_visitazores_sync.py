"""Visit Azores trails sync tests."""

from unittest.mock import patch

from django.test import TestCase

from trails.models import Trail, TrailStage
from trails.visitazores_sync import (
    fetch_pt_translation,
    gpx_to_linestring,
    gpx_to_stages,
    gpx_to_waypoints,
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
<div class="field field-name-field-category"><div class="field-item even">Category - Circular</div></div>
<div class="field field-name-field-time-average"><div class="field-item even">Time average - 3h 00min</div></div>
<div class="field field-name-body"><div class="field-item even" property="content:encoded"><p>English trail description here.</p></div></div>
<div class="field field-name-field-gpx-file"><a href="https://trails.visitazores.com/sites/default/files/trails/sao-miguel/prc29smi.gpx">GPS</a></div>
<div class="field field-name-field-kml-file"><a href="https://trails.visitazores.com/sites/default/files/trails/sao-miguel/prc29smi.kml">KML</a></div>
<div class="field field-name-field-map-file"><a href="https://trails.visitazores.com/sites/default/files/trails/sao-miguel/prc29smi.png">Map</a></div>
<div class="field field-name-field-downloads"><a href="https://trails.visitazores.com/sites/default/files/prc29smi-folheto.pdf">Leaflet</a></div>
<div id="geofield-map-entity-node-86"></div>
PRC29SMI
</body></html>
"""

SAMPLE_PT_HTML = """
<html><head>
<meta property="og:title" content="Caldeiras da Ribeira Grande - Salto do Cabrito | Trilhos dos Açores" />
</head><body>
<div class="field field-name-body"><div class="field-item even" property="content:encoded"><p>Descrição portuguesa do trilho.</p></div></div>
</body></html>
"""

SAMPLE_GPX = """<?xml version="1.0"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1">
<wpt lat="37.797842" lon="-25.487155"><name>PRC29 SMI</name><sym>Trail Head</sym></wpt>
<wpt lat="37.797351" lon="-25.487305"><name>CALDEIRAS DA RIBEIRA GRANDE</name></wpt>
<trk><name>PRC29 SMI Caldeiras</name><trkseg>
<trkpt lat="37.78" lon="-25.50"/>
<trkpt lat="37.79" lon="-25.49"/>
</trkseg></trk>
</gpx>"""

SAMPLE_MULTI_GPX = """<?xml version="1.0"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1">
<trk><name>Stage One</name><trkseg>
<trkpt lat="37.78" lon="-25.50"/><trkpt lat="37.79" lon="-25.49"/>
</trkseg></trk>
<trk><name>Stage Two</name><trkseg>
<trkpt lat="37.80" lon="-25.48"/><trkpt lat="37.81" lon="-25.47"/>
</trkseg></trk>
</gpx>"""


class VisitAzoresSyncTestCase(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        self.island.feature_flags = {**self.island.feature_flags, 'trails': True}
        self.island.save()

    @patch('trails.visitazores_sync._download_gpx_text', return_value=SAMPLE_GPX)
    def test_parse_trail_detail_page_extracts_fields(self, _mock_gpx):
        with patch('trails.visitazores_sync.fetch_pt_translation', return_value={'description_pt': 'PT desc'}):
            row = parse_trail_detail_page(SAMPLE_DETAIL_HTML, page_url='https://example.test/trail')
        assert row is not None
        self.assertEqual(row['source_ref'], 'PRC29SMI')
        self.assertEqual(row['name'], 'Caldeiras da Ribeira Grande - Salto do Cabrito')
        self.assertEqual(row['difficulty'], 'moderate')
        self.assertEqual(row['distance_km'], 8.6)
        self.assertEqual(row['shape'], 'circular')
        self.assertEqual(row['duration_min'], 180)
        self.assertEqual(row['description_en'], 'English trail description here.')
        self.assertEqual(row['description_pt'], 'PT desc')
        self.assertIn('.gpx', row['gpx_url'])
        self.assertIn('.kml', row['kml_url'])
        self.assertIn('.png', row['map_image_url'])
        self.assertIn('.pdf', row['leaflet_url'])
        self.assertEqual(row['start_lat'], 37.78)
        self.assertEqual(row['start_lon'], -25.50)
        self.assertEqual(len(row['waypoints']), 2)
        self.assertEqual(row['geojson']['type'], 'LineString')

    def test_gpx_to_linestring(self):
        geometry = gpx_to_linestring(SAMPLE_GPX)
        assert geometry is not None
        self.assertEqual(geometry['coordinates'][0], [-25.50, 37.78])

    def test_gpx_to_waypoints_skips_nameless(self):
        gpx = """<?xml version="1.0"?><gpx xmlns="http://www.topografix.com/GPX/1/1">
        <wpt lat="1" lon="2"/><wpt lat="3" lon="4"><name>Named</name></wpt></gpx>"""
        waypoints = gpx_to_waypoints(gpx)
        self.assertEqual(len(waypoints), 1)
        self.assertEqual(waypoints[0]['name'], 'Named')

    def test_gpx_to_stages_multi_track_only(self):
        self.assertEqual(gpx_to_stages(SAMPLE_GPX), [])
        stages = gpx_to_stages(SAMPLE_MULTI_GPX)
        self.assertEqual(len(stages), 2)
        self.assertEqual(stages[0]['name'], 'Stage One')

    def test_fetch_pt_translation(self):
        with patch('trails.visitazores_sync._get_html', return_value=SAMPLE_PT_HTML):
            payload = fetch_pt_translation(86)
        self.assertIn('Descrição portuguesa', payload['description_pt'])

    @patch('trails.visitazores_sync.fetch_island_trail_paths', return_value=['/en/trails-azores/sao-miguel/test'])
    @patch('trails.visitazores_sync._get_html', return_value=SAMPLE_DETAIL_HTML)
    @patch('trails.visitazores_sync._download_gpx_text', return_value=SAMPLE_GPX)
    @patch('trails.visitazores_sync.fetch_pt_translation', return_value={'description_pt': 'PT desc'})
    def test_sync_visitazores_trails_for_island(self, *_mocks):
        counts = sync_visitazores_trails_for_island(self.island)
        self.assertEqual(counts['created'], 1)
        self.assertEqual(counts['skipped'], 0)
        trail = Trail.objects.get(source_ref='PRC29SMI')
        self.assertEqual(trail.shape, 'circular')
        self.assertEqual(trail.duration_min, 180)
        self.assertEqual(TrailStage.objects.filter(trail=trail).count(), 0)

    @patch('trails.visitazores_sync.fetch_island_trail_paths', return_value=['/en/trails-azores/sao-miguel/test'])
    @patch('trails.visitazores_sync._get_html', return_value=SAMPLE_DETAIL_HTML)
    @patch('trails.visitazores_sync._download_gpx_text', return_value=SAMPLE_MULTI_GPX)
    @patch('trails.visitazores_sync.fetch_pt_translation', return_value={})
    def test_sync_creates_stages_for_multi_track_gpx(self, *_mocks):
        sync_visitazores_trails_for_island(self.island)
        trail = Trail.objects.get(source_ref='PRC29SMI')
        stages = list(TrailStage.objects.filter(trail=trail).order_by('sequence'))
        self.assertEqual(len(stages), 2)
        self.assertEqual(stages[0].name, 'Stage One')
