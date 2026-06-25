"""Route weather service tests."""

from datetime import datetime
from unittest.mock import patch

from django.test import TestCase, override_settings

from tenancy.services import get_or_create_default_island
from transit.services.route_weather import get_route_weather
from transit.tests.fixtures import ensure_transit_fixtures
from weather.models import Parish
from weather.tests.test_weather import SAMPLE_HOURLY_RAW, SAMPLE_RAW

LOC_MEM_CACHE = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}


class RouteWeatherServiceTestCase(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.island, _trip, _line = ensure_transit_fixtures()
        Parish.objects.get_or_create(
            island=self.island,
            slug='test-route-weather-pdl',
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
            slug='test-route-weather-rg',
            defaults={
                'name': 'Ribeira Seca',
                'concelho': 'Ribeira Grande',
                'latitude': 37.8219,
                'longitude': -25.5186,
                'is_active': True,
            },
        )

    @override_settings(CACHES=LOC_MEM_CACHE)
    @patch(
        'weather.services.fetch_forecast',
        side_effect=lambda coords: [SAMPLE_RAW] * len(coords),
    )
    def test_get_route_weather_current_mode(self, _mock_forecast):
        payload = get_route_weather(
            self.island,
            origin='Ponta Delgada',
            destination='Ribeira Grande',
        )

        self.assertIsNotNone(payload['origin'])
        self.assertIsNotNone(payload['destination'])
        assert payload['origin'] is not None
        assert payload['destination'] is not None
        self.assertEqual(payload['origin']['source'], 'current')
        self.assertEqual(payload['destination']['source'], 'current')
        self.assertIn('distanceKm', payload['origin'])
        self.assertIn('distanceKm', payload['destination'])

    @override_settings(CACHES=LOC_MEM_CACHE)
    @patch('weather.services.fetch_hourly', return_value=SAMPLE_HOURLY_RAW)
    @patch(
        'weather.services.fetch_forecast',
        side_effect=lambda coords: [SAMPLE_RAW] * len(coords),
    )
    def test_get_route_weather_forecast_mode(self, _mock_forecast, _mock_hourly):
        origin_at = datetime.fromisoformat('2026-06-03T08:30:00')
        destination_at = datetime.fromisoformat('2026-06-03T09:15:00')
        payload = get_route_weather(
            self.island,
            origin='Ponta Delgada',
            destination='Ribeira Grande',
            origin_at=origin_at,
            destination_at=destination_at,
        )

        self.assertIsNotNone(payload['origin'])
        self.assertIsNotNone(payload['destination'])
        assert payload['origin'] is not None
        assert payload['destination'] is not None
        self.assertEqual(payload['origin']['source'], 'forecast')
        self.assertEqual(payload['origin']['at'], '2026-06-03T08:30')
        self.assertEqual(payload['destination']['source'], 'forecast')
        self.assertEqual(payload['destination']['at'], '2026-06-03T09:15')

    @override_settings(CACHES=LOC_MEM_CACHE)
    @patch(
        'weather.services.fetch_forecast',
        side_effect=lambda coords: [SAMPLE_RAW] * len(coords),
    )
    def test_get_route_weather_null_cell_beyond_forecast(self, _mock_forecast):
        origin_at = datetime.fromisoformat('2026-06-10T08:30:00')
        payload = get_route_weather(
            self.island,
            origin='Ponta Delgada',
            destination='Ribeira Grande',
            origin_at=origin_at,
            destination_at=None,
        )

        self.assertIsNone(payload['origin'])
        self.assertIsNotNone(payload['destination'])

    @override_settings(CACHES=LOC_MEM_CACHE)
    @patch(
        'weather.services.fetch_forecast',
        side_effect=lambda coords: [SAMPLE_RAW] * len(coords),
    )
    def test_get_route_weather_unknown_stop_returns_null_cell(self, _mock_forecast):
        payload = get_route_weather(
            self.island,
            origin='Unknown Stop XYZ',
            destination='Ribeira Grande',
        )

        self.assertIsNone(payload['origin'])
        self.assertIsNotNone(payload['destination'])

    @override_settings(CACHES=LOC_MEM_CACHE)
    @patch(
        'weather.services.fetch_forecast',
        side_effect=lambda coords: [SAMPLE_RAW] * len(coords),
    )
    def test_get_route_weather_quartel_maps_to_arrifes_not_ajuda(self, _mock_forecast):
        from transit.models import Stop

        Stop.objects.get_or_create(
            island=self.island,
            cleaned_name='quartel',
            defaults={
                'name': 'Quartel',
                'latitude': 37.7758512621779,
                'longitude': -25.70775245961612,
            },
        )
        ajuda, _ = Parish.objects.update_or_create(
            island=self.island,
            slug='ajuda-da-bretanha-ponta-delgada',
            defaults={
                'name': 'Ajuda da Bretanha',
                'concelho': 'Ponta Delgada',
                'latitude': 37.89874231024076,
                'longitude': -25.75499373056614,
                'is_active': True,
            },
        )
        arrifes, _ = Parish.objects.update_or_create(
            island=self.island,
            slug='arrifes-ponta-delgada',
            defaults={
                'name': 'Arrifes',
                'concelho': 'Ponta Delgada',
                'latitude': 37.7675,
                'longitude': -25.6975,
                'is_active': True,
            },
        )

        payload = get_route_weather(
            self.island,
            origin='Quartel',
            destination='Ribeira Grande',
        )

        self.assertIsNotNone(payload['origin'])
        assert payload['origin'] is not None
        self.assertEqual(payload['origin']['slug'], arrifes.slug)
        self.assertNotEqual(payload['origin']['slug'], ajuda.slug)
