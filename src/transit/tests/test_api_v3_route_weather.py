"""Transit v3 route-weather API tests."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from transit.tests.fixtures import ensure_transit_fixtures
from weather.models import Parish
from weather.open_meteo_client import OpenMeteoError
from weather.tests.test_weather import SAMPLE_RAW

LOC_MEM_CACHE = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}


class TransitRouteWeatherAPITests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.client = APIClient()
        self.island, _trip, _line = ensure_transit_fixtures()
        self.island.is_live = True
        self.island.feature_flags = {
            **(self.island.feature_flags or {}),
            'transit': True,
            'weather': True,
        }
        self.island.save(update_fields=['is_live', 'feature_flags'])
        self.headers = {'HTTP_X_ISLAND': 'sao-miguel'}
        Parish.objects.get_or_create(
            island=self.island,
            slug='test-api-route-weather-pdl',
            defaults={
                'name': 'São Pedro',
                'concelho': 'Ponta Delgada',
                'latitude': 37.7411,
                'longitude': -25.6756,
                'is_active': True,
            },
        )
        Parish.objects.get_or_create(
            island=self.island,
            slug='test-api-route-weather-rg',
            defaults={
                'name': 'Ribeira Seca',
                'concelho': 'Ribeira Grande',
                'latitude': 37.8219,
                'longitude': -25.5186,
                'is_active': True,
            },
        )

    def test_route_weather_requires_island(self):
        with override_settings(DEFAULT_ISLAND_KEY='missing-island'):
            response = self.client.get(
                '/api/v3/transit/route-weather',
                {'origin': 'Ponta Delgada', 'destination': 'Ribeira Grande'},
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], 'island_required')

    @patch('transit.api_v3.get_route_weather')
    def test_route_weather_happy_path(self, mock_get_route_weather):
        mock_get_route_weather.return_value = {
            'origin': {'slug': 'origin-slug', 'source': 'current'},
            'destination': {'slug': 'dest-slug', 'source': 'current'},
        }
        response = self.client.get(
            '/api/v3/transit/route-weather',
            {'origin': 'Ponta Delgada', 'destination': 'Ribeira Grande'},
            **self.headers,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['origin']['slug'], 'origin-slug')
        self.assertEqual(body['destination']['slug'], 'dest-slug')
        mock_get_route_weather.assert_called_once()

    @patch('transit.api_v3.get_route_weather', side_effect=OpenMeteoError('upstream'))
    def test_route_weather_open_meteo_error(self, _mock_get_route_weather):
        response = self.client.get(
            '/api/v3/transit/route-weather',
            {'origin': 'Ponta Delgada', 'destination': 'Ribeira Grande'},
            **self.headers,
        )
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()['error']['code'], 'weather_unavailable')

    @override_settings(CACHES=LOC_MEM_CACHE)
    @patch(
        'weather.services.fetch_forecast',
        side_effect=lambda coords: [SAMPLE_RAW] * len(coords),
    )
    def test_route_weather_integration(self, _mock_forecast):
        response = self.client.get(
            '/api/v3/transit/route-weather',
            {'origin': 'Ponta Delgada', 'destination': 'Ribeira Grande'},
            **self.headers,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['origin']['source'], 'current')
        self.assertEqual(body['destination']['source'], 'current')
