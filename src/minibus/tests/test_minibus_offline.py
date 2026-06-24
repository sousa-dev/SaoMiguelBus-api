"""Mini Bus offline-bundle snapshot tests."""

from django.test import TestCase
from rest_framework.test import APIClient

from minibus.models import MinibusLine
from minibus.services import compute_bundle_version, route_shapes_revision, seed_catalog
from tenancy.services import get_or_create_default_island


class OfflineBundleApiTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.island = get_or_create_default_island()
        flags = dict(self.island.feature_flags or {})
        flags['minibus'] = True
        self.island.feature_flags = flags
        self.island.save(update_fields=['feature_flags'])
        seed_catalog(self.island)

    def test_bundle_contains_all_offline_sections(self):
        response = self.client.get('/api/v3/minibus/offline-bundle?locale=pt', HTTP_X_ISLAND='sao-miguel')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body['lines']), 4)
        self.assertEqual(len(body['tariffs']), 8)
        self.assertEqual(len(body['network']['lines']), 4)
        self.assertIn('attribution', body)
        self.assertTrue(body['version'])

    def test_bundle_images_point_at_line_png_files(self):
        response = self.client.get('/api/v3/minibus/offline-bundle', HTTP_X_ISLAND='sao-miguel')
        body = response.json()
        self.assertEqual(len(body['images']), 4)
        line_a = next(img for img in body['images'] if img['line_code'] == 'A')
        self.assertEqual(line_a['slug'], 'line-a')
        self.assertTrue(line_a['url'].endswith('/api/v3/minibus/documents/line-a/file'))

    def test_bundle_includes_network_map_png(self):
        response = self.client.get('/api/v3/minibus/offline-bundle', HTTP_X_ISLAND='sao-miguel')
        body = response.json()
        self.assertIsNotNone(body['network_map'])
        self.assertEqual(body['network_map']['slug'], 'network-map')
        self.assertTrue(body['network_map']['url'].endswith('/api/v3/minibus/documents/network-map/file'))

    def test_bundle_network_stops_include_coordinates(self):
        response = self.client.get('/api/v3/minibus/offline-bundle', HTTP_X_ISLAND='sao-miguel')
        body = response.json()
        line_a = next(line for line in body['network']['lines'] if line['code'] == 'A')
        stop = line_a['stops'][0]
        self.assertIsNotNone(stop.get('latitude'))
        self.assertIsNotNone(stop.get('longitude'))

    def test_version_endpoint_matches_bundle_version(self):
        version = compute_bundle_version(self.island)
        response = self.client.get('/api/v3/minibus/offline-bundle/version', HTTP_X_ISLAND='sao-miguel')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['version'], version)

    def test_version_is_stable_across_calls(self):
        first = compute_bundle_version(self.island)
        second = compute_bundle_version(self.island)
        self.assertEqual(first, second)

    def test_bundle_version_changes_when_route_shapes_update(self):
        before = compute_bundle_version(self.island)
        line = MinibusLine.objects.get(island=self.island, code='A')
        line.route_shapes = [
            {
                'direction': 0,
                'encoded_polyline': 'uxieF~tt{CLMRA',
                'journey_id': '1',
                'source_vehicle_id': '11010943',
                'captured_at': '2026-06-24T18:51:45+00:00',
            },
        ]
        line.save(update_fields=['route_shapes'])
        after = compute_bundle_version(self.island)
        self.assertNotEqual(before, after)
        self.assertNotEqual(route_shapes_revision(self.island), 'e3b0c44298fc1c14')

    def test_offline_bundle_includes_route_shapes(self):
        line = MinibusLine.objects.get(island=self.island, code='C')
        line.route_shapes = [
            {
                'direction': 0,
                'encoded_polyline': 'uxieF~tt{CLMRA',
                'journey_id': '3',
                'source_vehicle_id': '11010936',
                'captured_at': '2026-06-24T18:51:45+00:00',
            },
        ]
        line.save(update_fields=['route_shapes'])

        response = self.client.get('/api/v3/minibus/offline-bundle', HTTP_X_ISLAND='sao-miguel')
        body = response.json()
        line_c = next(row for row in body['lines'] if row['code'] == 'C')
        self.assertEqual(len(line_c['route_shapes']), 1)
