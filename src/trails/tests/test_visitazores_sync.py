"""Visit Azores trails sync tests."""

from unittest.mock import patch

from django.test import TestCase

from trails.models import Trail, TrailStage
from trails.visitazores_sync import (
    VISITAZORES_ISLAND_SLUGS,
    _parse_trail_ref,
    fetch_pt_translation,
    gpx_to_linestring,
    gpx_to_stages,
    gpx_to_waypoints,
    parse_trail_detail_page,
    sync_visitazores_trails_for_island,
)
from tenancy.models import Island
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

# Faial's real trail shape: a 'PRC4FAI' ref (the suffix REF_PATTERN used to be missing) and
# geometry over Faial rather than São Miguel, so this also exercises the per-island bbox.
FAIAL_DETAIL_HTML = """
<html><head>
<meta property="og:title" content="Caldeira | Azores Trails" />
<script>jQuery.extend(Drupal.settings, {"geofieldMap":{"map":{"data":{"type":"LineString","coordinates":[[-28.7200,38.5800],[-28.7100,38.5850]]}}}});</script>
</head><body>
<div class="field field-name-field-difficulty"><div class="field-item even">Difficulty - Easy</div></div>
<div class="field field-name-field-extension"><div class="field-item even">Extension - 6.8 km</div></div>
<div class="field field-name-field-category"><div class="field-item even">Category - Circular</div></div>
<div class="field field-name-field-time-average"><div class="field-item even">Time average - 2h 30min</div></div>
<div class="field field-name-body"><div class="field-item even" property="content:encoded"><p>Around the Caldeira.</p></div></div>
<div class="field field-name-field-gpx-file"><a href="https://trails.visitazores.com/sites/default/files/trails/faial/prc4fai.gpx">GPS</a></div>
<div class="field field-name-field-map-file"><a href="https://trails.visitazores.com/sites/default/files/trails/faial/prc4fai.png">Map</a></div>
<div id="geofield-map-entity-node-50"></div>
PRC4FAI
</body></html>
"""

FAIAL_GPX = """<?xml version="1.0"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1">
<wpt lat="38.5800" lon="-28.7200"><name>PRC4 FAI</name><sym>Trail Head</sym></wpt>
<trk><name>PRC4 FAI Caldeira</name><trkseg>
<trkpt lat="38.5800" lon="-28.7200"/>
<trkpt lat="38.5850" lon="-28.7100"/>
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


class VisitAzoresRefPatternTestCase(TestCase):
    """REF_PATTERN gates everything: parse_trail_detail_page() returns None on an unparsed
    ref, so a missing island suffix drops those trails silently. It shipped with 'FLW' (no
    such suffix — Flores is 'FLO') and no 'FAI' at all, losing all 14 Faial + Flores trails."""

    # One real ref per island, taken from the live listings.
    REAL_REFS = {
        'sao-miguel': 'PRC29SMI',
        'santa-maria': 'PR2SMA',
        'terceira': 'PRC5TER',
        'graciosa': 'PR1GRA',
        'sao-jorge': 'PR7SJO',
        'pico': 'PR9PIC',
        'faial': 'PRC4FAI',
        'flores': 'PR2FLO',
        'corvo': 'PRC1COR',
    }

    def test_parses_a_ref_for_every_island(self):
        for island_key, ref in self.REAL_REFS.items():
            with self.subTest(island=island_key):
                self.assertEqual(_parse_trail_ref(f'<p>{ref}</p>'), ref)

    def test_parses_multi_digit_and_zero_padded_refs(self):
        # Faial ships both PR10FAI and PRC09FAI.
        self.assertEqual(_parse_trail_ref('<p>PR10FAI</p>'), 'PR10FAI')
        self.assertEqual(_parse_trail_ref('<p>PRC09FAI</p>'), 'PRC09FAI')

    def test_rejects_unknown_island_suffix(self):
        self.assertEqual(_parse_trail_ref('<p>PRC1XXX</p>'), '')

    def test_every_slug_maps_to_a_seeded_island(self):
        seeded = set(Island.objects.values_list('key', flat=True))
        self.assertEqual(set(VISITAZORES_ISLAND_SLUGS) - seeded, set())

    def test_covers_all_nine_islands(self):
        self.assertEqual(set(VISITAZORES_ISLAND_SLUGS), set(self.REAL_REFS))


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

    def test_parse_trail_detail_page_strips_missing_translation_placeholder(self):
        html = SAMPLE_DETAIL_HTML.replace(
            'English trail description here.',
            'No site não aparece o texto em ingles.',
        )
        with patch('trails.visitazores_sync.fetch_pt_translation', return_value={'description_pt': 'Descrição real.'}):
            row = parse_trail_detail_page(html, page_url='https://example.test/trail')
        assert row is not None
        self.assertEqual(row['description_en'], '')
        self.assertEqual(row['description_pt'], 'Descrição real.')

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

    @patch('trails.visitazores_sync.fetch_island_trail_paths', return_value=['/en/trails-azores/faial/caldeira'])
    @patch('trails.visitazores_sync._get_html', return_value=FAIAL_DETAIL_HTML)
    @patch('trails.visitazores_sync._download_gpx_text', return_value=FAIAL_GPX)
    @patch('trails.visitazores_sync.fetch_pt_translation', return_value={'description_pt': 'Caldeira do Faial.'})
    def test_sync_imports_a_non_sao_miguel_island(self, *_mocks):
        """End-to-end proof for the eight islands Hub never synced. Before the REF_PATTERN fix
        this asserted zero created: 'PRC4FAI' did not parse, so parse_trail_detail_page()
        returned None and every Faial trail was dropped as skipped."""
        faial = Island.objects.get(key='faial')
        counts = sync_visitazores_trails_for_island(faial)

        self.assertEqual(counts['created'], 1)
        self.assertEqual(counts['skipped'], 0)

        trail = Trail.objects.filter(island=faial, source_ref='PRC4FAI').first()
        assert trail is not None
        self.assertEqual(trail.name, 'Caldeira')
        self.assertEqual(trail.distance_km, 6.8)
        self.assertEqual(trail.duration_min, 150)
        self.assertEqual(trail.shape, 'circular')
        # Geometry must survive feature_in_island() against Faial's own bbox, not São Miguel's.
        self.assertEqual(trail.geojson['type'], 'LineString')
        self.assertAlmostEqual(trail.start_lat, 38.5800, places=3)

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
