"""Tests for minibus live tracking health probe."""

from __future__ import annotations

from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from pathlib import Path
from rest_framework.test import APIClient

from minibus.services import seed_catalog
from minibus.services_tracking import get_tracking_health
from minibus.tracking_client import MinibusTrackingError
from tenancy.services import get_or_create_default_island


FLEET_FIXTURE = [
    {
        'id': '11010939',
        'position': {'lat': 37.750218, 'lon': -25.667546},
        'status': 'ontime',
        'color': '00964C',
    },
    {
        'id': '11010940',
        'position': {'lat': 37.751, 'lon': -25.668},
        'status': 'ontime',
        'color': '00964C',
    },
]


@override_settings(MEDIA_ROOT='/tmp/smb-minibus-tracking-health-test-media')
class MinibusTrackingHealthServiceTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.island = get_or_create_default_island()

    def tearDown(self):
        cache.clear()

    @patch('minibus.services_tracking.fetch_fleet_locations')
    def test_probe_success(self, mock_fetch):
        mock_fetch.return_value = FLEET_FIXTURE

        result = get_tracking_health(self.island)

        self.assertTrue(result['available'])
        self.assertEqual(result['vehicleCount'], 2)
        self.assertEqual(result['recheckAfterSeconds'], 30)
        self.assertIn('checkedAt', result)

    @patch('minibus.services_tracking.fetch_fleet_locations')
    def test_probe_upstream_403(self, mock_fetch):
        mock_fetch.side_effect = MinibusTrackingError('Upstream HTTP 403')

        result = get_tracking_health(self.island)

        self.assertFalse(result['available'])
        self.assertEqual(result['reason'], 'upstream_http_403')

    @patch('minibus.services_tracking.fetch_fleet_locations')
    def test_cache_hit_avoids_second_upstream_call(self, mock_fetch):
        mock_fetch.return_value = FLEET_FIXTURE

        get_tracking_health(self.island)
        get_tracking_health(self.island)

        mock_fetch.assert_called_once()

    @patch('minibus.services_tracking.fetch_fleet_locations')
    def test_force_bypasses_cache_read(self, mock_fetch):
        mock_fetch.return_value = FLEET_FIXTURE

        get_tracking_health(self.island)
        get_tracking_health(self.island, force=True)

        self.assertEqual(mock_fetch.call_count, 2)

    @patch('minibus.services_tracking.fetch_fleet_locations')
    def test_negative_result_cached(self, mock_fetch):
        mock_fetch.side_effect = MinibusTrackingError('Upstream HTTP 403')

        first = get_tracking_health(self.island)
        second = get_tracking_health(self.island)

        self.assertFalse(first['available'])
        self.assertFalse(second['available'])
        mock_fetch.assert_called_once()


@override_settings(MEDIA_ROOT='/tmp/smb-minibus-tracking-health-api-test-media')
class MinibusTrackingHealthApiTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.island = get_or_create_default_island()
        flags = dict(self.island.feature_flags or {})
        flags['minibus'] = True
        self.island.feature_flags = flags
        self.island.save(update_fields=['feature_flags'])
        seed_catalog(self.island)
        source_dir = Path(__file__).resolve().parent.parent / 'data' / 'source'
        call_command('import_minibus', island='sao-miguel', source_dir=str(source_dir), skip_seed=True)

    def tearDown(self):
        cache.clear()

    def test_health_requires_island_context(self):
        with override_settings(DEFAULT_ISLAND_KEY='missing-island'):
            response = self.client.get('/api/v3/minibus/tracking/health')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], 'island_required')

    @patch('minibus.api_v3.get_tracking_health')
    def test_health_available(self, mock_get_health):
        mock_get_health.return_value = {
            'available': True,
            'checkedAt': '2026-06-22T12:00:00+00:00',
            'recheckAfterSeconds': 30,
            'vehicleCount': 5,
        }

        response = self.client.get('/api/v3/minibus/tracking/health', HTTP_X_ISLAND='sao-miguel')

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['available'])
        self.assertEqual(body['vehicleCount'], 5)
        mock_get_health.assert_called_once()
        self.assertFalse(mock_get_health.call_args.kwargs.get('force'))

    @patch('minibus.api_v3.get_tracking_health')
    def test_health_unavailable(self, mock_get_health):
        mock_get_health.return_value = {
            'available': False,
            'reason': 'upstream_http_403',
            'checkedAt': '2026-06-22T12:00:00+00:00',
            'recheckAfterSeconds': 30,
        }

        response = self.client.get('/api/v3/minibus/tracking/health', HTTP_X_ISLAND='sao-miguel')

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body['available'])
        self.assertEqual(body['reason'], 'upstream_http_403')

    @patch('minibus.api_v3.get_tracking_health')
    def test_health_force_query_param(self, mock_get_health):
        mock_get_health.return_value = {
            'available': False,
            'reason': 'upstream_http_403',
            'checkedAt': '2026-06-22T12:00:00+00:00',
            'recheckAfterSeconds': 30,
        }

        response = self.client.get(
            '/api/v3/minibus/tracking/health?force=1',
            HTTP_X_ISLAND='sao-miguel',
        )

        self.assertEqual(response.status_code, 200)
        mock_get_health.assert_called_once()
        self.assertTrue(mock_get_health.call_args.kwargs.get('force'))
