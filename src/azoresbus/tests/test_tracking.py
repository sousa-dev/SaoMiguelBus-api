"""02 §8: three distinct states, and conflating them is the easy mistake.

    tracking_disabled   flag off            -> 503
    empty fleet         nobody reporting    -> 200 []
    upstream failure    AVL down            -> 502

The fleet is [] today and that is the CORRECT answer, not an error. Ships dark:
the flag is off, so the entry point simply does not exist for clients.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

import requests
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from azoresbus.services_tracking import fleet_cache_key, get_tracking_config
from azoresbus.tracking_client import (
    serialize_fleet_vehicle,
    serialize_vehicle_detail,
)
from shared.live_counts import read_live_count
from tenancy.services import get_or_create_default_island

HEADERS = {'HTTP_X_ISLAND': 'sao-miguel'}
LOC_MEM_CACHE = {
    'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
}

# 98 claim 14: the exact key sets, list vs detail.
# Note `status` vs `busStatus`: upstream puts PUNCTUALITY in `status` on the list
# and the MOVEMENT state in `busStatus`, then swaps `status` to the movement
# state on the detail. This fixture keeps them deliberately different so a
# serializer that reads the wrong one fails loudly.
LIST_ITEM = {'id': '11010934', 'position': {'lat': 37.74, 'lon': -25.66},
             'status': 'ontime', 'busStatus': 'idleAt', 'delay': 0,
             'speed': 0.0, 'color': 'EC6E00'}
# Deliberately out of sequence order, and stop 19 has no dueInMinutes because
# upstream omits it for stops already passed.
CIRCULATIONS = [
    {'sequence': 21, 'stage': {'id': '31', 'name': 'FURNAS (CALDEIRAS)',
                               'nameShort': '4033',
                               'position': {'lat': 37.77, 'lon': -25.30}},
     'departureTime': 33300, 'arrivalTime': 33300, 'dueInMinutes': 3},
    {'sequence': 19, 'stage': {'id': '29', 'name': 'FURNAS (POLICIA)',
                               'nameShort': '4052',
                               'position': {'lat': 37.77, 'lon': -25.31}},
     'departureTime': 33216, 'arrivalTime': 33216},
    {'sequence': 20, 'stage': {'id': '30', 'name': 'FURNAS (PQ. CAMPISMO)',
                               'nameShort': '4051',
                               'position': {'lat': 37.77, 'lon': -25.31}},
     'departureTime': 33146, 'arrivalTime': 33146, 'dueInMinutes': 0},
]
DETAIL = {
    'id': '11010934', 'fleetId': '25', 'licensePlate': '',
    'position': {'lat': 37.74, 'lon': -25.66}, 'speed': 2.81,
    'status': 'incomingAt', 'currentStopSequence': 20,
    'route': {'id': '4', 'name': 'LINHA D', 'nameShort': 'D',
              'color': 'EC6E00', 'isActive': False},
    'journey': {'id': '5', 'type': 'frequency', 'shape': 'myieF',
                'name': '08:35 >> 09:05', 'start': '08:35', 'end': '09:05',
                'startTime': 30900, 'endTime': 32700, 'direction': 1,
                'isActive': True, 'circulations': CIRCULATIONS},
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
        """Age the envelope past its TTL rather than deleting it.

        Deleting the cache key would remove the stale copy along with the fresh
        one, so the assertion below would pass for the wrong reason -- 502 is
        also "not a blank map". Expiry is what we mean, so expiry is what we
        simulate.
        """
        self._flag(True)
        mock_get.return_value = MagicMock(
            ok=True, status_code=200, json=lambda: [LIST_ITEM], text='',
        )
        self.client.get('/api/v3/azoresbus/vehicles', **HEADERS)

        key = fleet_cache_key(self.island.key)
        envelope = cache.get(key)
        self.assertIsNotNone(envelope, 'the first call should have cached a fleet')
        # Past the TTL but inside the stale grace: exactly the window this
        # behaviour exists to cover.
        cfg = get_tracking_config()
        envelope['fetched_at'] = (
            timezone.now() - timedelta(seconds=cfg['cache_ttl'] + 5)
        ).isoformat()
        cache.set(key, envelope, 6000)

        mock_get.side_effect = requests.RequestException('blip')
        response = self.client.get('/api/v3/azoresbus/vehicles', **HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['vehicles']), 1)

    @patch('azoresbus.tracking_client.requests.get')
    def test_a_long_outage_stops_pretending_and_returns_502(self, mock_get):
        """Stale grace is a grace, not a licence to serve yesterday's map."""
        self._flag(True)
        mock_get.return_value = MagicMock(
            ok=True, status_code=200, json=lambda: [LIST_ITEM], text='',
        )
        self.client.get('/api/v3/azoresbus/vehicles', **HEADERS)

        key = fleet_cache_key(self.island.key)
        envelope = cache.get(key)
        envelope['fetched_at'] = (
            timezone.now() - timedelta(hours=2)
        ).isoformat()
        cache.set(key, envelope, 7200)

        mock_get.side_effect = requests.RequestException('sustained outage')
        response = self.client.get('/api/v3/azoresbus/vehicles', **HEADERS)
        self.assertEqual(response.status_code, 502)

    @patch('azoresbus.tracking_client.requests.get')
    def test_vehicle_detail_is_cached(self, mock_get):
        """Re-opening the same bus within the TTL must not re-hit the Pi."""
        self._flag(True)
        mock_get.return_value = MagicMock(
            ok=True, status_code=200, json=lambda: DETAIL, text='',
        )
        first = self.client.get(
            '/api/v3/azoresbus/vehicles/11010934', **HEADERS,
        )
        calls_after_first = mock_get.call_count
        second = self.client.get(
            '/api/v3/azoresbus/vehicles/11010934', **HEADERS,
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(mock_get.call_count, calls_after_first)

    @patch('azoresbus.tracking_client.requests.get')
    def test_health_verdict_is_cached(self, mock_get):
        self._flag(True)
        mock_get.return_value = MagicMock(
            ok=True, status_code=200, json=lambda: [LIST_ITEM], text='',
        )
        self.client.get('/api/v3/azoresbus/tracking/health', **HEADERS)
        after_first = mock_get.call_count

        self.client.get('/api/v3/azoresbus/tracking/health', **HEADERS)
        self.assertEqual(mock_get.call_count, after_first)

    @patch('azoresbus.tracking_client.requests.get')
    def test_force_re_probes_upstream_when_the_fleet_has_expired(self, mock_get):
        """"Try again" must actually try again.

        Force bypasses the health VERDICT cache only; the fleet keeps its own
        short TTL underneath. That is deliberate rather than a half-measure: the
        Try Again button is only ever on screen while tracking is unavailable,
        and in that state there is no fresh fleet to be served -- so the forced
        call reaches upstream, which is the whole point. An unforced call in the
        same state would sit on the cached failure verdict and look broken.
        """
        self._flag(True)
        mock_get.return_value = MagicMock(
            ok=True, status_code=200, json=lambda: [LIST_ITEM], text='',
        )
        self.client.get('/api/v3/azoresbus/tracking/health', **HEADERS)

        # Age the fleet past its TTL, as it would be by the time a user reads an
        # error and reaches for the button.
        key = fleet_cache_key(self.island.key)
        envelope = cache.get(key)
        # Past the real TTL, whatever it is configured to be -- a hard-coded
        # number here silently stops testing anything when the cadence changes.
        expired_by = get_tracking_config()['cache_ttl'] + 5
        envelope['fetched_at'] = (
            timezone.now() - timedelta(seconds=expired_by)
        ).isoformat()
        cache.set(key, envelope, 6000)
        before = mock_get.call_count

        self.client.get('/api/v3/azoresbus/tracking/health', **HEADERS)
        self.assertEqual(
            mock_get.call_count, before,
            'an unforced call should still be sitting on the cached verdict',
        )

        self.client.get('/api/v3/azoresbus/tracking/health?force=1', **HEADERS)
        self.assertGreater(mock_get.call_count, before)

    @patch('azoresbus.tracking_client.requests.get')
    def test_routes_are_served_even_while_tracking_is_disabled(self, mock_get):
        """The catalogue is network reference data, not a tracking privilege."""
        self._flag(False)
        mock_get.return_value = MagicMock(
            ok=True, status_code=200, text='',
            json=lambda: [
                {'id': '2', 'nameShort': '102', 'name': 'PDL - RG',
                 'color': '2D59A9', 'isActive': True},
                {'id': '1', 'nameShort': '101', 'name': 'PDL - RIBEIRINHA',
                 'color': '2D59A9', 'isActive': True},
            ],
        )
        response = self.client.get('/api/v3/azoresbus/routes', **HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [r['nameShort'] for r in response.json()['routes']], ['101', '102'],
        )

    @patch('azoresbus.tracking_client.requests.get')
    def test_routes_degrade_to_empty_rather_than_erroring(self, mock_get):
        self._flag(True)
        mock_get.side_effect = requests.RequestException('catalogue down')
        response = self.client.get('/api/v3/azoresbus/routes', **HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['routes'], [])


class LiveCountRecordingTests(TestCase):
    """`GET /vehicles` is a real vendor touch on a cache miss -- it must feed
    the shared live-counts record other hub screens read for free."""

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

    @patch('azoresbus.tracking_client.requests.get')
    def test_fleet_miss_records_live_count(self, mock_get):
        self._flag(True)
        mock_get.return_value = MagicMock(
            ok=True, status_code=200, json=lambda: [LIST_ITEM], text='',
        )
        self.client.get('/api/v3/azoresbus/vehicles', **HEADERS)

        record = read_live_count('azoresbus', self.island.key)
        self.assertEqual(record['status'], 'ok')
        self.assertEqual(record['vehicles'], 1)

    @patch('azoresbus.services_tracking.fetch_fleet_locations')
    def test_fleet_hit_re_records_without_a_new_vendor_call(self, mock_fetch):
        # Mocked at the fleet-fetch level (not the raw HTTP client) so route
        # enrichment's own per-vehicle lookups can't be mistaken for a second
        # fleet call.
        self._flag(True)
        mock_fetch.return_value = [LIST_ITEM]

        self.client.get('/api/v3/azoresbus/vehicles', **HEADERS)
        first = read_live_count('azoresbus', self.island.key)
        self.client.get('/api/v3/azoresbus/vehicles', **HEADERS)
        second = read_live_count('azoresbus', self.island.key)

        # Same underlying fetch, so the record's timestamp does not advance --
        # a HIT must not look like a fresher vendor call than it was.
        self.assertEqual(first['recordedAt'], second['recordedAt'])
        mock_fetch.assert_called_once()

    @patch('azoresbus.tracking_client.requests.get')
    def test_upstream_failure_records_outage(self, mock_get):
        self._flag(True)
        mock_get.side_effect = requests.RequestException('down')

        self.client.get('/api/v3/azoresbus/vehicles', **HEADERS)

        record = read_live_count('azoresbus', self.island.key)
        self.assertEqual(record['status'], 'unavailable')
        self.assertIsNone(record['vehicles'])

    def test_flag_off_records_nothing(self):
        self._flag(False)

        self.client.get('/api/v3/azoresbus/vehicles', **HEADERS)

        self.assertIsNone(read_live_count('azoresbus', self.island.key))

    def test_health_reports_disabled_without_calling_upstream(self):
        self._flag(False)
        with patch('azoresbus.tracking_client.requests.get') as mock_get:
            response = self.client.get(
                '/api/v3/azoresbus/tracking/health', **HEADERS,
            )
        mock_get.assert_not_called()
        self.assertEqual(response.json()['status'], 'disabled')


class TrackingConfigTests(TestCase):
    def test_the_stale_window_is_not_empty(self):
        """Stale-serve only exists while `cache_ttl < age <= stale_grace`.

        Raising the TTL to the poll cadence without raising the grace closed
        that window entirely once already: the fallback silently stopped
        existing, and a one-off upstream blip would blank a working map. The
        relationship matters, not the numbers, so assert the relationship.
        """
        cfg = get_tracking_config()
        self.assertGreater(
            cfg['stale_grace'], cfg['cache_ttl'],
            'stale grace must outlast the TTL or a blip blanks the map',
        )


class SerializerShapeTests(TestCase):
    """List and detail are DIFFERENT key sets; one serializer would blur them."""

    def test_list_has_colour_at_the_top_level(self):
        payload = serialize_fleet_vehicle(LIST_ITEM)
        self.assertEqual(
            sorted(payload),
            ['busStatus', 'color', 'delay', 'id', 'position', 'route', 'speed',
             'status'],
        )

    def test_list_carries_movement_state_not_only_punctuality(self):
        """Dropping busStatus makes every bus read "on time" forever.

        `status` is punctuality on the list, so a fleet row built from it alone
        can never say "at the stop" -- which is the one thing a waiting rider
        actually wants to know.
        """
        payload = serialize_fleet_vehicle(LIST_ITEM)
        self.assertEqual(payload['status'], 'ontime')
        self.assertEqual(payload['busStatus'], 'idleAt')

    def test_list_route_is_a_slot_for_the_index_to_fill(self):
        """Present-but-None, so the key set does not depend on cache warmth."""
        payload = serialize_fleet_vehicle(LIST_ITEM)
        self.assertIn('route', payload)
        self.assertIsNone(payload['route'])

    def test_detail_has_no_top_level_colour(self):
        payload = serialize_vehicle_detail(DETAIL)
        self.assertNotIn('color', payload)
        self.assertEqual(payload['route']['color'], 'EC6E00')

    def test_detail_carries_the_join_keys(self):
        """currentStopSequence + journey.id are what map a bus to our data."""
        payload = serialize_vehicle_detail(DETAIL)
        self.assertEqual(payload['currentStopSequence'], 20)
        self.assertEqual(payload['journey']['id'], '5')
        self.assertEqual(payload['journey']['direction'], 1)

    def test_detail_carries_circulations_in_sequence_order(self):
        """The ETA list is the reason the detail call exists."""
        payload = serialize_vehicle_detail(DETAIL)
        circulations = payload['journey']['circulations']
        self.assertEqual([c['sequence'] for c in circulations], [19, 20, 21])
        self.assertEqual(
            circulations[0]['stage']['name'], 'FURNAS (POLICIA)',
        )
        self.assertEqual(circulations[0]['stage']['position']['lat'], 37.77)

    def test_a_passed_stop_keeps_a_null_due_rather_than_being_dropped(self):
        """None means "behind us", not "unknown" -- the row still renders."""
        payload = serialize_vehicle_detail(DETAIL)
        by_sequence = {
            c['sequence']: c for c in payload['journey']['circulations']
        }
        self.assertIsNone(by_sequence[19]['dueInMinutes'])
        self.assertEqual(by_sequence[20]['dueInMinutes'], 0)
        self.assertEqual(by_sequence[21]['dueInMinutes'], 3)

    def test_a_vehicle_between_journeys_serialises_without_circulations(self):
        payload = serialize_vehicle_detail(
            {**DETAIL, 'journey': {'id': '5', 'type': 'frequency'}},
        )
        self.assertEqual(payload['journey']['circulations'], [])
