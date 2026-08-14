"""02 §8: three distinct states, and conflating them is the easy mistake.

    tracking_disabled   flag off            -> 503
    empty fleet         nobody reporting    -> 200 []
    upstream failure    AVL down            -> 502

The fleet is [] today and that is the CORRECT answer, not an error. Ships dark:
the flag is off, so the entry point simply does not exist for clients.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from azoresbus.tracking_client import (
    serialize_fleet_vehicle,
    serialize_vehicle_detail,
)
from tenancy.services import get_or_create_default_island

HEADERS = {'HTTP_X_ISLAND': 'sao-miguel'}
LOC_MEM_CACHE = {
    'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
}

# 98 claim 14: the exact key sets, list vs detail.
LIST_ITEM = {'id': '11010934', 'position': {'lat': 37.74, 'lon': -25.66},
             'status': 'ontime', 'color': 'EC6E00'}
DETAIL = {
    'id': '11010934', 'fleetId': '25', 'licensePlate': '',
    'position': {'lat': 37.74, 'lon': -25.66}, 'speed': 2.81,
    'status': 'incomingAt', 'currentStopSequence': 20,
    'route': {'id': '4', 'name': 'LINHA D', 'nameShort': 'D',
              'color': 'EC6E00', 'isActive': False},
    'journey': {'id': '5', 'type': 'frequency', 'shape': 'myieF'},
}


@override_settings(CACHES=LOC_MEM_CACHE)
class TrackingEndpointTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.island = get_or_create_default_island()

    def _flag(self, enabled: bool):
        self.island.feature_flags = {
            **(self.island.feature_flags or {}),
            'azoresbus': {'trackingEnabled': enabled},
        }
        self.island.save(update_fields=['feature_flags'])

    def test_flag_off_returns_503_tracking_disabled(self):
        self._flag(False)
        response = self.client.get('/api/v3/azoresbus/vehicles', **HEADERS)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()['error']['code'], 'tracking_disabled',
        )

    @patch('azoresbus.tracking_client.requests.get')
    def test_flag_on_with_an_empty_fleet_is_200_not_an_error(self, mock_get):
        """[] means nobody is reporting. That is the answer today."""
        self._flag(True)
        mock_get.return_value = MagicMock(
            ok=True, status_code=200, json=lambda: [], text='',
        )
        response = self.client.get('/api/v3/azoresbus/vehicles', **HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['vehicles'], [])

    @patch('azoresbus.tracking_client.requests.get')
    def test_upstream_failure_is_502_not_an_empty_fleet(self, mock_get):
        self._flag(True)
        mock_get.side_effect = requests.RequestException('down')
        response = self.client.get('/api/v3/azoresbus/vehicles', **HEADERS)
        self.assertEqual(response.status_code, 502)

    @patch('azoresbus.tracking_client.requests.get')
    def test_a_blip_serves_the_stale_fleet_rather_than_blanking_the_map(
        self, mock_get,
    ):
        self._flag(True)
        mock_get.return_value = MagicMock(
            ok=True, status_code=200, json=lambda: [LIST_ITEM], text='',
        )
        self.client.get('/api/v3/azoresbus/vehicles', **HEADERS)
        cache.delete('azoresbus:tracking:fleet')       # TTL expiry

        mock_get.side_effect = requests.RequestException('blip')
        response = self.client.get('/api/v3/azoresbus/vehicles', **HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['vehicles']), 1)

    def test_health_reports_disabled_without_calling_upstream(self):
        self._flag(False)
        with patch('azoresbus.tracking_client.requests.get') as mock_get:
            response = self.client.get(
                '/api/v3/azoresbus/tracking/health', **HEADERS,
            )
        mock_get.assert_not_called()
        self.assertEqual(response.json()['status'], 'disabled')


class SerializerShapeTests(TestCase):
    """List and detail are DIFFERENT key sets; one serializer would blur them."""

    def test_list_has_colour_at_the_top_level(self):
        payload = serialize_fleet_vehicle(LIST_ITEM)
        self.assertEqual(
            sorted(payload), ['color', 'id', 'position', 'status'],
        )

    def test_detail_has_no_top_level_colour(self):
        payload = serialize_vehicle_detail(DETAIL)
        self.assertNotIn('color', payload)
        self.assertEqual(payload['route']['color'], 'EC6E00')

    def test_detail_carries_the_join_keys(self):
        """currentStopSequence + journey.id are what map a bus to our data."""
        payload = serialize_vehicle_detail(DETAIL)
        self.assertEqual(payload['currentStopSequence'], 20)
        self.assertEqual(payload['journey']['id'], '5')
