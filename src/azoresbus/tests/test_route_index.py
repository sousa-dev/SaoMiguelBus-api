"""The route index: what the fleet list cannot tell us on its own.

The two behaviours worth defending here are negative ones -- enrichment must not
be able to fail a working fleet, and must not be able to stampede the upstream --
so most of these tests assert about what did NOT happen.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

import requests
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from azoresbus.services_route_index import (
    merge_index,
    prune_index,
    stale_ids,
)
from tenancy.services import get_or_create_default_island

HEADERS = {'HTTP_X_ISLAND': 'sao-miguel'}
LOC_MEM_CACHE = {
    'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
}

LIST_ITEM = {'id': '11011199', 'position': {'lat': 37.74, 'lon': -25.66},
             'status': 'ontime', 'busStatus': 'inTransitTo', 'delay': 0,
             'speed': 8.1, 'color': '2D59A9'}
DETAIL = {
    'id': '11011199', 'fleetId': '3609', 'licensePlate': '',
    'position': {'lat': 37.74, 'lon': -25.66}, 'speed': 8.1,
    'status': 'inTransitTo', 'currentStopSequence': 2,
    'route': {'id': '7', 'name': 'PONTA DELGADA - FURNAS',
              'nameShort': '110', 'color': '2D59A9', 'isActive': True},
    'journey': {'id': '1861', 'type': 'scheduled', 'shape': 'cyoeF'},
}


class StaleIdsTests(TestCase):
    def setUp(self):
        self.now = timezone.now()

    def _entry(self, age_seconds: int) -> dict:
        return {
            'route': {'id': '7'},
            'refreshed_at': (
                self.now - timedelta(seconds=age_seconds)
            ).isoformat(),
        }

    def test_a_fresh_entry_is_left_alone(self):
        index = {'a': self._entry(10)}
        self.assertEqual(stale_ids(index, ['a'], 180, self.now), [])

    def test_never_seen_vehicles_come_before_merely_stale_ones(self):
        """Under a deadline, ordering is the policy.

        An unknown bus shows no line at all; a stale one still shows the right
        line almost always. So the unknown ones must be fetched first.
        """
        index = {'stale': self._entry(900)}
        order = stale_ids(index, ['stale', 'brand-new'], 180, self.now)
        self.assertEqual(order, ['brand-new', 'stale'])

    def test_stale_entries_are_ordered_oldest_first(self):
        index = {
            'recent': self._entry(200),
            'ancient': self._entry(5000),
            'middling': self._entry(600),
        }
        order = stale_ids(
            index, ['recent', 'ancient', 'middling'], 180, self.now,
        )
        self.assertEqual(order, ['ancient', 'middling', 'recent'])

    def test_a_corrupt_timestamp_is_treated_as_never_seen(self):
        index = {'a': {'route': {'id': '7'}, 'refreshed_at': 'not-a-date'}}
        self.assertEqual(stale_ids(index, ['a'], 180, self.now), ['a'])


class MergeIndexTests(TestCase):
    def test_a_failed_lookup_keeps_the_previous_answer(self):
        """A miss must not downgrade a bus from "line 110" to "unknown"."""
        now = timezone.now()
        index = {'a': {'route': {'id': '7'}, 'refreshed_at': now.isoformat()}}
        merged = merge_index(index, {'a': None}, now)
        self.assertEqual(merged['a']['route'], {'id': '7'})

    def test_a_successful_lookup_replaces_and_restamps(self):
        now = timezone.now()
        earlier = (now - timedelta(hours=1)).isoformat()
        index = {'a': {'route': {'id': '1'}, 'refreshed_at': earlier}}
        merged = merge_index(index, {'a': {'id': '7'}}, now)
        self.assertEqual(merged['a']['route'], {'id': '7'})
        self.assertEqual(merged['a']['refreshed_at'], now.isoformat())


class PruneIndexTests(TestCase):
    def test_a_bus_that_left_service_is_eventually_forgotten(self):
        now = timezone.now()
        index = {
            'retired': {'route': {'id': '1'},
                        'refreshed_at': (now - timedelta(hours=3)).isoformat()},
            'live': {'route': {'id': '7'}, 'refreshed_at': now.isoformat()},
        }
        kept = prune_index(index, ['live'], 1800, now)
        self.assertEqual(sorted(kept), ['live'])

    def test_a_bus_that_just_blinked_out_is_kept(self):
        """The fleet churns all day; a gap is not a retirement."""
        now = timezone.now()
        index = {
            'blinked': {'route': {'id': '7'},
                        'refreshed_at': (now - timedelta(seconds=60)).isoformat()},
        }
        kept = prune_index(index, [], 1800, now)
        self.assertEqual(sorted(kept), ['blinked'])


@override_settings(CACHES=LOC_MEM_CACHE)
class EnrichmentEndpointTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.island = get_or_create_default_island()
        self.island.feature_flags = {
            **(self.island.feature_flags or {}),
            'azoresbus': {'trackingEnabled': True},
        }
        self.island.save(update_fields=['feature_flags'])

    def _upstream(self, mock_get):
        """Route /locations to the fleet and /locations/<id> to the detail."""
        def _response(url, **_kwargs):
            payload = DETAIL if url.rstrip('/').endswith(DETAIL['id']) else [LIST_ITEM]
            return MagicMock(ok=True, status_code=200,
                             json=lambda: payload, text='')
        mock_get.side_effect = _response

    @patch('azoresbus.tracking_client.requests.get')
    def test_the_fleet_gains_a_line(self, mock_get):
        self._upstream(mock_get)
        response = self.client.get('/api/v3/azoresbus/vehicles', **HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()['vehicles'][0]['route']['nameShort'], '110',
        )

    @patch('azoresbus.tracking_client.requests.get')
    def test_an_unindexed_vehicle_is_shown_without_a_line_not_hidden(
        self, mock_get,
    ):
        """A bus we cannot label is still a bus on the map."""
        def _response(url, **_kwargs):
            if url.rstrip('/').endswith(DETAIL['id']):
                raise requests.RequestException('detail down')
            return MagicMock(ok=True, status_code=200,
                             json=lambda: [LIST_ITEM], text='')
        mock_get.side_effect = _response

        response = self.client.get('/api/v3/azoresbus/vehicles', **HEADERS)
        self.assertEqual(response.status_code, 200)
        vehicles = response.json()['vehicles']
        self.assertEqual(len(vehicles), 1)
        self.assertIsNone(vehicles[0]['route'])

    @patch('azoresbus.services_route_index._sweep')
    @patch('azoresbus.tracking_client.requests.get')
    def test_enrichment_blowing_up_does_not_fail_the_fleet(
        self, mock_get, mock_sweep,
    ):
        self._upstream(mock_get)
        mock_sweep.side_effect = RuntimeError('index exploded')

        response = self.client.get('/api/v3/azoresbus/vehicles', **HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['vehicles']), 1)

    @patch('azoresbus.services_route_index._fetch_route_for')
    @patch('azoresbus.tracking_client.requests.get')
    def test_the_sweep_is_rate_limited_between_polls(
        self, mock_get, mock_fetch_route,
    ):
        """Two polls in quick succession must cost one sweep, not two."""
        self._upstream(mock_get)
        mock_fetch_route.return_value = {'id': '7', 'nameShort': '110',
                                         'name': 'PDL - FURNAS',
                                         'color': '2D59A9'}

        self.client.get('/api/v3/azoresbus/vehicles', **HEADERS)
        after_first = mock_fetch_route.call_count
        cache.delete(f'azoresbus:tracking:fleet:{self.island.key}')
        self.client.get('/api/v3/azoresbus/vehicles', **HEADERS)

        self.assertEqual(after_first, 1)
        self.assertEqual(mock_fetch_route.call_count, after_first)
