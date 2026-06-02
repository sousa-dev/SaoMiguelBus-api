"""Trails v3 API tests."""

from django.test import TestCase
from rest_framework.test import APIClient

from trails.models import POI, Trail
from tenancy.services import get_or_create_default_island


class TrailsAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.island = get_or_create_default_island()
        self.island.feature_flags = {
            **self.island.feature_flags,
            'trails': True,
            'transit': True,
        }
        self.island.save()
        self.headers = {'HTTP_X_ISLAND': 'sao-miguel'}
        self.trail_a = Trail.objects.create(
            island=self.island,
            source_ref='trail-a',
            name='Alpha Trail',
            difficulty='easy',
            distance_km=3.2,
            geojson={'type': 'LineString', 'coordinates': [[-25.5, 37.78], [-25.49, 37.79]]},
        )
        self.trail_b = Trail.objects.create(
            island=self.island,
            source_ref='trail-b',
            name='Beta Trail',
            difficulty='hard',
            distance_km=8.0,
            geojson={'type': 'LineString', 'coordinates': [[-25.51, 37.77], [-25.48, 37.80]]},
        )
        self.poi = POI.objects.create(
            island=self.island,
            source_ref='poi-1',
            name='Miradouro',
            category='Miradouro',
            latitude=37.78,
            longitude=-25.50,
        )

    def test_list_trails_ordered_by_name(self):
        response = self.client.get('/api/v3/trails/', **self.headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn('attribution', body)
        trails = body['trails']
        self.assertEqual(trails[0]['name'], 'Alpha Trail')
        self.assertEqual(trails[1]['name'], 'Beta Trail')
        self.assertNotIn('geojson', trails[0])

    def test_list_trails_difficulty_filter(self):
        response = self.client.get('/api/v3/trails/?difficulty=hard', **self.headers)
        self.assertEqual(response.status_code, 200)
        trails = response.json()['trails']
        self.assertEqual(len(trails), 1)
        self.assertEqual(trails[0]['id'], self.trail_b.id)

    def test_detail_includes_geojson(self):
        response = self.client.get(f'/api/v3/trails/{self.trail_a.id}', **self.headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['geojson']['type'], 'LineString')
        self.assertEqual(body['stages'], [])
        self.assertIn('attribution', body)

    def test_detail_not_found(self):
        response = self.client.get('/api/v3/trails/99999', **self.headers)
        self.assertEqual(response.status_code, 404)

    def test_list_pois_with_category_filter(self):
        response = self.client.get('/api/v3/trails/pois?category=Mira', **self.headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body['pois']), 1)
        self.assertEqual(body['pois'][0]['name'], 'Miradouro')

    def test_default_island_when_header_missing(self):
        response = self.client.get('/api/v3/trails/')
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.json()['trails']), 1)
