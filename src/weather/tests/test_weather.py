"""Weather module tests."""

import json
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from tenancy.services import get_or_create_default_island
from weather.models import Parish
from weather.open_meteo_client import Coord, OpenMeteoError
from weather.services import ATTRIBUTION, refresh_parishes, serialize_parish_weather

SAMPLE_HOURLY_RAW = {
    'hourly': {
        'time': [f'2026-06-03T{h:02d}:00' for h in range(24)],
        'temperature_2m': [18.0 + (h % 5) for h in range(24)],
        'weather_code': [1] * 24,
        'wind_speed_10m': [12.0] * 24,
        'relative_humidity_2m': [70] * 24,
        'precipitation': [0.0] * 24,
        'precipitation_probability': [15] * 24,
    },
}

SAMPLE_RAW = {
    'current': {
        'time': '2026-06-03T12:00',
        'temperature_2m': 18.5,
        'weather_code': 1,
        'wind_speed_10m': 12.0,
        'relative_humidity_2m': 70,
        'precipitation': 0.0,
    },
    'daily': {
        'time': ['2026-06-03', '2026-06-04', '2026-06-05'],
        'weather_code': [1, 2, 3],
        'temperature_2m_max': [20.0, 21.0, 19.0],
        'temperature_2m_min': [15.0, 16.0, 14.0],
        'precipitation_probability_max': [10, 20, 30],
    },
}

GAZETTEER_PATH = Path(__file__).resolve().parent.parent / 'data' / 'parishes_sao_miguel.json'


class GazetteerTestCase(TestCase):
    def test_gazetteer_shape(self):
        with GAZETTEER_PATH.open(encoding='utf-8') as handle:
            rows = json.load(handle)
        self.assertGreaterEqual(len(rows), 64)
        slugs = {row['slug'] for row in rows}
        self.assertEqual(len(slugs), len(rows))
        concelhos = {
            'Ponta Delgada',
            'Ribeira Grande',
            'Lagoa',
            'Vila Franca do Campo',
            'Povoação',
            'Nordeste',
        }
        for row in rows:
            self.assertIn(row['concelho'], concelhos)
            self.assertGreaterEqual(row['lat'], 37.7)
            self.assertLessEqual(row['lat'], 37.9)
            self.assertGreaterEqual(row['lon'], -25.9)
            self.assertLessEqual(row['lon'], -25.1)


class OpenMeteoClientTestCase(TestCase):
    @patch('weather.open_meteo_client.requests.get')
    def test_fetch_forecast_builds_multi_coord_params(self, mock_get):
        mock_get.return_value.ok = True
        mock_get.return_value.json.return_value = [SAMPLE_RAW, SAMPLE_RAW]

        from weather.open_meteo_client import fetch_forecast

        coords = [Coord(37.74, -25.67), Coord(37.82, -25.52)]
        result = fetch_forecast(coords)
        self.assertEqual(len(result), 2)
        params = mock_get.call_args.kwargs['params']
        self.assertEqual(params['latitude'], '37.74,37.82')
        self.assertEqual(params['longitude'], '-25.67,-25.52')

    def test_fetch_forecast_empty_coords(self):
        from weather.open_meteo_client import fetch_forecast

        self.assertEqual(fetch_forecast([]), [])

    @patch('weather.open_meteo_client.requests.get')
    def test_fetch_forecast_http_error(self, mock_get):
        mock_get.return_value.ok = False
        mock_get.return_value.status_code = 500
        mock_get.return_value.text = 'error'

        from weather.open_meteo_client import fetch_forecast

        with self.assertRaises(OpenMeteoError):
            fetch_forecast([Coord(37.74, -25.67)])

    @patch('weather.open_meteo_client.requests.get')
    def test_fetch_hourly_builds_params(self, mock_get):
        mock_get.return_value.ok = True
        mock_get.return_value.json.return_value = SAMPLE_HOURLY_RAW

        from weather.open_meteo_client import fetch_hourly

        result = fetch_hourly(Coord(37.74, -25.67), forecast_days=2)
        self.assertIn('hourly', result)
        params = mock_get.call_args.kwargs['params']
        self.assertEqual(params['latitude'], '37.74')
        self.assertEqual(params['longitude'], '-25.67')
        self.assertEqual(params['forecast_days'], '2')
        self.assertIn('temperature_2m', params['hourly'])

    @patch('weather.open_meteo_client.requests.get')
    def test_fetch_hourly_http_error(self, mock_get):
        mock_get.return_value.ok = False
        mock_get.return_value.status_code = 503
        mock_get.return_value.text = 'unavailable'

        from weather.open_meteo_client import fetch_hourly

        with self.assertRaises(OpenMeteoError):
            fetch_hourly(Coord(37.74, -25.67), forecast_days=1)

    @patch('weather.open_meteo_client.requests.get')
    def test_fetch_hourly_malformed_payload(self, mock_get):
        mock_get.return_value.ok = True
        mock_get.return_value.json.return_value = {'hourly': {'time': []}}

        from weather.open_meteo_client import fetch_hourly

        with self.assertRaises(OpenMeteoError):
            fetch_hourly(Coord(37.74, -25.67), forecast_days=1)


class WeatherServicesTestCase(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.island = get_or_create_default_island()
        self.parish = Parish.objects.create(
            island=self.island,
            name='Test Parish',
            slug='test-parish-ponta-delgada',
            concelho='Ponta Delgada',
            latitude=37.74,
            longitude=-25.67,
            is_active=True,
        )

    def test_serialize_parish_weather_maps_fields(self):
        out = serialize_parish_weather(self.parish, SAMPLE_RAW)
        self.assertEqual(out['slug'], self.parish.slug)
        self.assertEqual(out['current']['temperature'], 18.5)
        self.assertEqual(len(out['daily']), 3)
        self.assertEqual(out['attribution'], ATTRIBUTION)

    @override_settings(
        CACHES={
            'default': {
                'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            }
        },
    )
    @patch('weather.services.fetch_forecast', return_value=[SAMPLE_RAW])
    def test_refresh_parishes_sets_cache(self, _mock_fetch):
        from weather.services import get_cached_parish_weather

        count = refresh_parishes([self.parish])
        self.assertEqual(count, 1)
        cached = get_cached_parish_weather(self.island.key, self.parish.slug)
        self.assertIsNotNone(cached)
        self.assertEqual(cached['current']['temperature'], 18.5)

    @override_settings(
        CACHES={
            'default': {
                'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            }
        },
    )
    @patch('weather.services.fetch_forecast', return_value=[SAMPLE_RAW])
    def test_list_parish_weather_uses_cache(self, mock_fetch):
        from weather.services import list_parish_weather

        first = list_parish_weather(self.island)
        second = list_parish_weather(self.island)
        self.assertEqual(len(first), 1)
        self.assertEqual(first, second)
        self.assertEqual(mock_fetch.call_count, 1)

    @patch('weather.services.fetch_forecast', return_value=[])
    def test_refresh_empty_parishes(self, _mock_fetch):
        self.assertEqual(refresh_parishes([]), 0)

    @override_settings(
        CACHES={
            'default': {
                'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            }
        },
    )
    @patch('weather.services.fetch_hourly', return_value=SAMPLE_HOURLY_RAW)
    @patch('weather.services.fetch_forecast', return_value=[SAMPLE_RAW])
    def test_get_parish_hourly_returns_slots(self, _mock_forecast, mock_hourly):
        from weather.services import get_parish_hourly

        refresh_parishes([self.parish])
        payload = get_parish_hourly(self.parish, '2026-06-03')
        self.assertEqual(payload['slug'], self.parish.slug)
        self.assertEqual(payload['date'], '2026-06-03')
        self.assertEqual(len(payload['hours']), 24)
        slot = payload['hours'][0]
        self.assertEqual(slot['time'], '2026-06-03T00:00')
        self.assertIn('temperature', slot)
        self.assertIn('weatherCode', slot)
        self.assertIn('precipitationProbability', slot)
        mock_hourly.assert_called_once()

    @override_settings(
        CACHES={
            'default': {
                'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            }
        },
    )
    @patch('weather.services.fetch_hourly', return_value=SAMPLE_HOURLY_RAW)
    @patch('weather.services.fetch_forecast', return_value=[SAMPLE_RAW])
    def test_get_parish_hourly_cache_hit(self, _mock_forecast, mock_hourly):
        from weather.services import get_parish_hourly

        refresh_parishes([self.parish])
        get_parish_hourly(self.parish, '2026-06-03')
        get_parish_hourly(self.parish, '2026-06-03')
        self.assertEqual(mock_hourly.call_count, 1)

    @override_settings(
        CACHES={
            'default': {
                'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            }
        },
    )
    @patch('weather.services.fetch_forecast', return_value=[SAMPLE_RAW])
    def test_get_parish_hourly_invalid_date(self, _mock_forecast):
        from weather.services import get_parish_hourly

        refresh_parishes([self.parish])
        with self.assertRaises(ValueError):
            get_parish_hourly(self.parish, '2026-06-10')

    @override_settings(
        CACHES={
            'default': {
                'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            }
        },
    )
    @patch('weather.services.fetch_hourly', return_value=SAMPLE_HOURLY_RAW)
    def test_get_parish_hourly_future_ttl(self, _mock_hourly):
        from django.core.cache import cache

        from weather.services import (
            HOURLY_TTL_FUTURE,
            _cache_key,
            get_parish_hourly,
        )

        cache.set(
            _cache_key(self.island.key, self.parish.slug),
            serialize_parish_weather(self.parish, SAMPLE_RAW),
            3600,
        )
        with patch.object(cache, 'set', wraps=cache.set) as mock_set:
            get_parish_hourly(self.parish, '2026-06-04')
            hourly_calls = [c for c in mock_set.call_args_list if ':hourly:' in c[0][0]]
        self.assertEqual(hourly_calls[0][0][2], HOURLY_TTL_FUTURE)

    @override_settings(
        CACHES={
            'default': {
                'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            }
        },
    )
    @patch('weather.services.fetch_hourly', return_value=SAMPLE_HOURLY_RAW)
    def test_get_parish_hourly_today_ttl(self, _mock_hourly):
        from django.core.cache import cache

        from weather.services import (
            HOURLY_TTL_TODAY,
            _cache_key,
            get_parish_hourly,
        )

        cache.set(
            _cache_key(self.island.key, self.parish.slug),
            serialize_parish_weather(self.parish, SAMPLE_RAW),
            3600,
        )
        with patch.object(cache, 'set', wraps=cache.set) as mock_set:
            get_parish_hourly(self.parish, '2026-06-03')
            hourly_calls = [c for c in mock_set.call_args_list if ':hourly:' in c[0][0]]
        self.assertEqual(hourly_calls[0][0][2], HOURLY_TTL_TODAY)


class WeatherAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.island = get_or_create_default_island()
        self.island.is_live = True
        self.island.feature_flags = {
            **self.island.feature_flags,
            'weather': True,
            'transit': True,
        }
        self.island.save()
        self.headers = {'HTTP_X_ISLAND': 'sao-miguel'}
        self.parish = Parish.objects.create(
            island=self.island,
            name='Test Parish',
            slug='test-parish-api',
            concelho='Ponta Delgada',
            latitude=37.74,
            longitude=-25.67,
            is_active=True,
        )

    @patch('weather.api_v3.list_parish_weather')
    def test_parishes_list(self, mock_list):
        payload = serialize_parish_weather(self.parish, SAMPLE_RAW)
        mock_list.return_value = [payload]
        response = self.client.get('/api/v3/weather/parishes', **self.headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body['parishes']), 1)
        self.assertEqual(body['attribution'], ATTRIBUTION)

    @patch('weather.api_v3.get_parish_weather')
    def test_parish_detail(self, mock_get):
        mock_get.return_value = serialize_parish_weather(self.parish, SAMPLE_RAW)
        response = self.client.get(
            f'/api/v3/weather/parishes/{self.parish.slug}',
            **self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['slug'], self.parish.slug)

    def test_parish_detail_not_found(self):
        response = self.client.get('/api/v3/weather/parishes/unknown-slug', **self.headers)
        self.assertEqual(response.status_code, 404)

    @patch('weather.api_v3.list_parish_weather', side_effect=OpenMeteoError('upstream'))
    def test_weather_unavailable(self, _mock):
        response = self.client.get('/api/v3/weather/parishes', **self.headers)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()['error']['code'], 'weather_unavailable')

    @patch('weather.api_v3.get_parish_hourly')
    def test_parish_hourly(self, mock_hourly):
        mock_hourly.return_value = {
            'slug': self.parish.slug,
            'date': '2026-06-03',
            'hours': [{'time': '2026-06-03T12:00', 'temperature': 18, 'weatherCode': 1}],
            'attribution': ATTRIBUTION,
        }
        response = self.client.get(
            f'/api/v3/weather/parishes/{self.parish.slug}/hourly?date=2026-06-03',
            **self.headers,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['date'], '2026-06-03')
        self.assertEqual(len(body['hours']), 1)

    def test_parish_hourly_missing_date(self):
        response = self.client.get(
            f'/api/v3/weather/parishes/{self.parish.slug}/hourly',
            **self.headers,
        )
        self.assertEqual(response.status_code, 400)

    @patch('weather.api_v3.get_parish_hourly', side_effect=ValueError('outside window'))
    def test_parish_hourly_invalid_date(self, _mock):
        response = self.client.get(
            f'/api/v3/weather/parishes/{self.parish.slug}/hourly?date=2026-06-10',
            **self.headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_parish_hourly_not_found(self):
        response = self.client.get(
            '/api/v3/weather/parishes/unknown-slug/hourly?date=2026-06-03',
            **self.headers,
        )
        self.assertEqual(response.status_code, 404)
