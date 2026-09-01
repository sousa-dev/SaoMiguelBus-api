"""API tests for minibus live vehicle tracking."""

from __future__ import annotations

from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from pathlib import Path
from rest_framework.test import APIClient

from minibus.services import seed_catalog
from minibus.services_tracking import CacheMeta
from minibus.tracking_client import MinibusTrackingError, MinibusTrackingNotFoundError
from tenancy.services import get_or_create_default_island


FLEET_FIXTURE = [
    {
        'id': '11010939',
        'position': {'lat': 37.750218, 'lon': -25.667546},
        'status': 'ontime',
        'color': '00964C',
    },
]

DETAIL_FIXTURE = {
    'id': '11010939',
    'position': {'lat': 37.750218, 'lon': -25.667546},
    'status': 'incomingAt',
    'currentStopSequence': 10,
    'journey': {
        'shape': 'uxieF~tt{CLMRA',
        'circulations': [
            {
                'sequence': 10,
                'stage': {'id': '210', 'nameShort': 'B 10'},
                'dueInMinutes': 0,
            },
        ],
    },
}


@override_settings(MEDIA_ROOT='/tmp/smb-minibus-tracking-test-media')
class MinibusTrackingApiTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.island = get_or_create_default_island()
        flags = dict(self.island.feature_flags or {})
        flags['minibus'] = True
        self.island.feature_flags = flags
        self.island.save(update_fields=['feature_flags'])
        seed_catalog(self.island)
        source_dir = Path(__file__).resolve().parent.parent / 'data' / 'source'
        call_command('import_minibus', island='sao-miguel', source_dir=str(source_dir), skip_seed=True)

    def test_vehicles_requires_island_context(self):
        with override_settings(DEFAULT_ISLAND_KEY='missing-island'):
            response = self.client.get('/api/v3/minibus/vehicles')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], 'island_required')

    @patch('minibus.api_v3.get_fleet_tracking')
    def test_vehicles_list_passthrough(self, mock_get_fleet):
        cached_at = timezone.now()
        mock_get_fleet.return_value = (
            FLEET_FIXTURE,
            CacheMeta(cached_at=cached_at, cache_status='miss', stale=False),
        )

        response = self.client.get('/api/v3/minibus/vehicles', HTTP_X_ISLAND='sao-miguel')

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['vehicles'], FLEET_FIXTURE)
        self.assertEqual(body['vehicles'][0]['id'], '11010939')
        # Also the client's poll cadence — see MINIBUS_TRACKING_CACHE_TTL.
        self.assertEqual(body['cacheMaxAgeSeconds'], 60)
        self.assertEqual(body['trackingCacheStatus'], 'miss')
        self.assertEqual(response['X-Minibus-Tracking-Cache'], 'miss')

    @patch.dict('os.environ', {'MINIBUS_TRACKING_CACHE_TTL': '5'})
    @patch('minibus.api_v3.get_fleet_tracking')
    def test_vehicles_list_cache_max_age_from_env(self, mock_get_fleet):
        cached_at = timezone.now()
        mock_get_fleet.return_value = (
            FLEET_FIXTURE,
            CacheMeta(cached_at=cached_at, cache_status='hit', stale=False),
        )

        response = self.client.get('/api/v3/minibus/vehicles', HTTP_X_ISLAND='sao-miguel')

        body = response.json()
        self.assertEqual(body['cacheMaxAgeSeconds'], 5)
        self.assertEqual(body['trackingCacheStatus'], 'hit')
        self.assertEqual(response['X-Minibus-Tracking-Cache'], 'hit')

    @patch('minibus.api_v3.get_vehicle_tracking')
    def test_vehicle_detail_passthrough(self, mock_get_vehicle):
        cached_at = timezone.now()
        mock_get_vehicle.return_value = (
            DETAIL_FIXTURE,
            CacheMeta(cached_at=cached_at, cache_status='miss', stale=False),
        )

        response = self.client.get(
            '/api/v3/minibus/vehicles/11010939',
            HTTP_X_ISLAND='sao-miguel',
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['vehicle']['journey']['shape'], 'uxieF~tt{CLMRA')
        self.assertEqual(body['vehicle']['currentStopSequence'], 10)
        self.assertEqual(
            body['vehicle']['journey']['circulations'][0]['dueInMinutes'],
            0,
        )

    @patch('minibus.api_v3.get_fleet_tracking')
    def test_vehicles_upstream_unavailable(self, mock_get_fleet):
        mock_get_fleet.side_effect = MinibusTrackingError('upstream down')

        response = self.client.get('/api/v3/minibus/vehicles', HTTP_X_ISLAND='sao-miguel')

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()['error']['code'], 'tracking_unavailable')

    @patch('minibus.api_v3.get_vehicle_tracking')
    def test_vehicle_detail_not_found(self, mock_get_vehicle):
        mock_get_vehicle.side_effect = MinibusTrackingNotFoundError('missing')

        response = self.client.get(
            '/api/v3/minibus/vehicles/missing',
            HTTP_X_ISLAND='sao-miguel',
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['error']['code'], 'tracking_not_found')

    @patch('minibus.api_v3.get_fleet_tracking')
    def test_vehicles_stale_response(self, mock_get_fleet):
        cached_at = timezone.now()
        mock_get_fleet.return_value = (
            FLEET_FIXTURE,
            CacheMeta(cached_at=cached_at, cache_status='stale', stale=True),
        )

        response = self.client.get('/api/v3/minibus/vehicles', HTTP_X_ISLAND='sao-miguel')

        body = response.json()
        self.assertTrue(body['stale'])
        self.assertEqual(body['trackingCacheStatus'], 'stale')
        self.assertEqual(response['X-Minibus-Tracking-Cache'], 'stale')
