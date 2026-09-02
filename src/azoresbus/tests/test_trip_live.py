from django.test import SimpleTestCase

from azoresbus.services_trip_live import (
    match_vehicles,
    next_stop_from_detail,
    parse_trip_ids,
    serialize_live_vehicle,
    upcoming_stops_from_detail,
)


class ParseTripIdsTests(SimpleTestCase):
    def test_dedupes_ignores_junk_and_caps_at_five(self):
        self.assertEqual(parse_trip_ids('3, 3,x,7,,8,9,10,11'), [3, 7, 8, 9, 10])

    def test_empty_and_none(self):
        self.assertEqual(parse_trip_ids(None), [])
        self.assertEqual(parse_trip_ids(''), [])


class MatchVehiclesTests(SimpleTestCase):
    def test_only_vehicles_in_service_and_journeys_asked_for(self):
        index = {
            'v1': {'journeyId': '1861', 'route': {}, 'refreshed_at': 'x'},
            'v2': {'journeyId': '1862', 'route': {}, 'refreshed_at': 'x'},
            'v3': {'journeyId': '1863', 'route': {}, 'refreshed_at': 'x'},
        }
        matches = match_vehicles(index, live_vehicle_ids=['v1', 'v3'], journey_ids=['1861', '1862'])
        self.assertEqual(matches, {'1861': 'v1'})

    def test_first_vehicle_wins_when_two_claim_one_journey(self):
        index = {
            'v1': {'journeyId': '1861'},
            'v2': {'journeyId': '1861'},
        }
        self.assertEqual(match_vehicles(index, ['v1', 'v2'], ['1861']), {'1861': 'v1'})


class NextStopTests(SimpleTestCase):
    RAW = {'journey': {'circulations': [
        {'sequence': 3, 'stage': {'id': '1115', 'name': 'FURNAS'}, 'dueInMinutes': None},
        {'sequence': 5, 'stage': {'id': '1140', 'name': 'RIBEIRA GRANDE'}, 'dueInMinutes': 9},
        {'sequence': 4, 'stage': {'id': '1134', 'name': 'CAMINHO NOVO'}, 'dueInMinutes': 2},
    ]}}

    def test_lowest_sequence_still_ahead_wins_and_identity_is_applied(self):
        identity = {'1134': {'stopId': 55, 'name': 'Caminho Novo'}}
        self.assertEqual(next_stop_from_detail(self.RAW, identity), {
            'sequence': 4, 'name': 'Caminho Novo', 'stopId': 55, 'dueInMinutes': 2,
        })

    def test_falls_back_to_upstream_name_and_none_when_all_passed(self):
        self.assertEqual(next_stop_from_detail(self.RAW, {})['name'], 'CAMINHO NOVO')
        self.assertIsNone(next_stop_from_detail({'journey': {'circulations': [
            {'sequence': 1, 'stage': {'id': '1'}, 'dueInMinutes': None},
        ]}}, {}))


class UpcomingStopsTests(SimpleTestCase):
    RAW = {'journey': {'circulations': [
        {'sequence': 3, 'stage': {'id': '1115', 'name': 'FURNAS'}, 'dueInMinutes': None},
        {'sequence': 5, 'stage': {'id': '1140', 'name': 'RIBEIRA GRANDE'}, 'dueInMinutes': 9},
        {'sequence': 4, 'stage': {'id': '1134', 'name': 'CAMINHO NOVO'}, 'dueInMinutes': 2},
    ]}}

    def test_returns_every_stop_still_ahead_sorted_by_sequence(self):
        identity = {'1134': {'stopId': 55, 'name': 'Caminho Novo'}}
        out = upcoming_stops_from_detail(self.RAW, identity)
        self.assertEqual(out, [
            {'sequence': 4, 'name': 'Caminho Novo', 'stopId': 55, 'dueInMinutes': 2},
            {'sequence': 5, 'name': 'RIBEIRA GRANDE', 'stopId': None, 'dueInMinutes': 9},
        ])

    def test_empty_when_nothing_is_ahead(self):
        raw = {'journey': {'circulations': [
            {'sequence': 1, 'stage': {'id': '1'}, 'dueInMinutes': None},
        ]}}
        self.assertEqual(upcoming_stops_from_detail(raw, {}), [])

    def test_next_stop_from_detail_is_the_first_of_the_list(self):
        self.assertEqual(
            next_stop_from_detail(self.RAW, {}),
            upcoming_stops_from_detail(self.RAW, {})[0],
        )


class SerializeLiveVehicleTests(SimpleTestCase):
    def test_shape(self):
        fleet_item = {'id': 'v1', 'position': {'lat': 37.8, 'lon': -25.5}, 'delay': 120}
        raw = {'id': 'v1', 'speed': 12.5, 'status': 'inTransitTo', 'currentStopSequence': 37}
        upcoming = [
            {'sequence': 38, 'name': 'X', 'stopId': 1, 'dueInMinutes': 3},
            {'sequence': 39, 'name': 'Y', 'stopId': 2, 'dueInMinutes': 7},
        ]
        out = serialize_live_vehicle(fleet_item, raw, '2026-09-02T10:00:00+00:00',
                                     upcoming, stale=False)
        self.assertEqual(sorted(out), ['capturedAt', 'currentStopSequence', 'delaySeconds', 'id',
                                       'nextStop', 'position', 'speed', 'stale', 'status',
                                       'upcomingStops'])
        self.assertEqual(out['position'], {'lat': 37.8, 'lon': -25.5})
        self.assertEqual(out['delaySeconds'], 120)
        self.assertEqual(out['currentStopSequence'], 37)
        self.assertEqual(out['nextStop'], upcoming[0])
        self.assertEqual(out['upcomingStops'], upcoming)

    def test_stale_without_detail(self):
        out = serialize_live_vehicle({'id': 'v1', 'position': {'lat': 1, 'lon': 2}, 'delay': None},
                                     {}, 'when', [], stale=True)
        self.assertEqual(out['id'], 'v1')
        self.assertTrue(out['stale'])
        self.assertIsNone(out['currentStopSequence'])
        self.assertIsNone(out['nextStop'])
        self.assertEqual(out['upcomingStops'], [])


from datetime import timedelta
from unittest.mock import MagicMock, patch

import requests
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from azoresbus.models import ExternalJourney
from azoresbus.services_route_index import _index_cache_key
from tenancy.services import get_or_create_default_island
from transit.models import DATASET_AZORESBUS, DATASET_LEGACY, Line, Operator, Trip

HEADERS = {'HTTP_X_ISLAND': 'sao-miguel'}
LOC_MEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}

FLEET = [{'id': '11', 'position': {'lat': 37.82, 'lon': -25.52}, 'status': 'delayed',
          'busStatus': 'inTransitTo', 'delay': 120, 'speed': 12.0, 'color': '2D59A9'}]


def _detail(journey_id: str) -> dict:
    return {
        'id': '11', 'fleetId': '3609', 'licensePlate': '',
        'position': {'lat': 37.82, 'lon': -25.52}, 'speed': 12.0,
        'status': 'inTransitTo', 'currentStopSequence': 3,
        'route': {'id': '9', 'nameShort': '110', 'name': 'PDL - RG', 'color': '2D59A9'},
        'journey': {'id': journey_id, 'type': 'scheduled', 'shape': '', 'name': '09:10 >> 10:40',
                    'start': '09:10:00', 'end': '10:40:00', 'startTime': 33000, 'endTime': 38400,
                    'direction': 1, 'isActive': True,
                    'circulations': [
                        {'sequence': 3, 'stage': {'id': '1115', 'name': 'A'}, 'dueInMinutes': None},
                        {'sequence': 4, 'stage': {'id': '1134', 'name': 'B'}, 'dueInMinutes': 2},
                    ]},
    }


@override_settings(CACHES=LOC_MEM_CACHE)
class TripsLiveEndpointTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.island = get_or_create_default_island()
        self.island.feature_flags = {'azoresbus': {'trackingEnabled': True}}
        self.island.save(update_fields=['feature_flags'])
        operator = Operator.objects.create(island=self.island, name='AzoresBus')
        line = Line.objects.create(island=self.island, dataset=DATASET_AZORESBUS, operator=operator, code='110')
        self.trip = Trip.objects.create(island=self.island, dataset=DATASET_AZORESBUS, line=line,
                                        calendar=None, service=None, source=Trip.SOURCE_OPERATOR)
        ExternalJourney.objects.create(island=self.island, dataset=DATASET_AZORESBUS,
                                       external_id='1861', route_ext_id='9', direction=1, trip=self.trip)
        self.legacy_trip = Trip.objects.create(island=self.island, dataset=DATASET_LEGACY, line=line,
                                               calendar=None, service=None, source=Trip.SOURCE_OPERATOR)

    def _seed_index(self, journey_id='1861'):
        cache.set(_index_cache_key(self.island.key), {
            '11': {'route': {'id': '9', 'nameShort': '110', 'name': '', 'color': '2D59A9'},
                   'journeyId': journey_id, 'refreshed_at': timezone.now().isoformat()},
        }, 600)

    @staticmethod
    def _upstream(detail_payload):
        def _response(url, **_kwargs):
            payload = detail_payload if url.rstrip('/').endswith('/11') else FLEET
            return MagicMock(ok=True, status_code=200, json=lambda: payload, text='')
        return _response

    def test_requires_trip_ids(self):
        response = self.client.get('/api/v3/azoresbus/trips/live', **HEADERS)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], 'trip_ids_required')

    def test_flag_off_is_503(self):
        self.island.feature_flags = {'azoresbus': {'trackingEnabled': False}}
        self.island.save(update_fields=['feature_flags'])
        response = self.client.get(f'/api/v3/azoresbus/trips/live?tripIds={self.trip.id}', **HEADERS)
        self.assertEqual(response.status_code, 503)

    @patch('azoresbus.tracking_client.requests.get')
    def test_live_match_carries_position_and_next_stop(self, mock_get):
        mock_get.side_effect = self._upstream(_detail('1861'))
        self._seed_index()
        response = self.client.get(
            f'/api/v3/azoresbus/trips/live?tripIds={self.trip.id},{self.legacy_trip.id}', **HEADERS,
        )
        self.assertEqual(response.status_code, 200)
        live, legacy = response.json()['trips']
        self.assertEqual(live['tripId'], self.trip.id)
        self.assertEqual(live['state'], 'live')
        self.assertEqual(live['vehicle']['position'], {'lat': 37.82, 'lon': -25.52})
        self.assertEqual(live['vehicle']['delaySeconds'], 120)
        self.assertEqual(live['vehicle']['currentStopSequence'], 3)
        self.assertEqual(live['vehicle']['nextStop']['dueInMinutes'], 2)
        self.assertEqual(live['vehicle']['upcomingStops'], [live['vehicle']['nextStop']])
        self.assertFalse(live['vehicle']['stale'])
        self.assertEqual(legacy, {'tripId': self.legacy_trip.id, 'state': 'unsupported', 'vehicle': None})

    @patch('azoresbus.tracking_client.requests.get')
    def test_index_lag_is_caught_by_the_detail(self, mock_get):
        """Index still says 1861 but the bus has started journey 1862."""
        mock_get.side_effect = self._upstream(_detail('1862'))
        self._seed_index('1861')
        response = self.client.get(f'/api/v3/azoresbus/trips/live?tripIds={self.trip.id}', **HEADERS)
        self.assertEqual(response.json()['trips'][0]['state'], 'not_found')

    @patch('azoresbus.tracking_client.requests.get')
    def test_cold_index_is_not_found_not_an_error(self, mock_get):
        mock_get.side_effect = self._upstream(_detail('1861'))
        # No index seeded: enrich_fleet will sweep, but the answer for THIS
        # request must still be a clean not_found rather than a hang or a 5xx.
        response = self.client.get(f'/api/v3/azoresbus/trips/live?tripIds={self.trip.id}', **HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertIn(response.json()['trips'][0]['state'], ('not_found', 'live'))

    @patch('azoresbus.tracking_client.requests.get')
    def test_unreadable_detail_degrades_to_stale_position(self, mock_get):
        def _response(url, **_kwargs):
            if url.rstrip('/').endswith('/11'):
                raise requests.RequestException('detail down')
            return MagicMock(ok=True, status_code=200, json=lambda: FLEET, text='')
        mock_get.side_effect = _response
        self._seed_index()
        response = self.client.get(f'/api/v3/azoresbus/trips/live?tripIds={self.trip.id}', **HEADERS)
        row = response.json()['trips'][0]
        self.assertEqual(row['state'], 'live')
        self.assertTrue(row['vehicle']['stale'])
        self.assertIsNone(row['vehicle']['nextStop'])
        self.assertEqual(row['vehicle']['upcomingStops'], [])

    @patch('azoresbus.tracking_client.requests.get')
    def test_upstream_down_is_502(self, mock_get):
        mock_get.side_effect = requests.RequestException('down')
        response = self.client.get(f'/api/v3/azoresbus/trips/live?tripIds={self.trip.id}', **HEADERS)
        self.assertEqual(response.status_code, 502)
