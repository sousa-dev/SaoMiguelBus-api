"""Live arrivals for a stop.

The behaviours worth defending are about honesty under partial information: a
bus we cannot re-read must not silently vanish, and one we can must not be
reported with a number we know is minutes old.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

import requests
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from azoresbus.models import ExternalStop
from azoresbus.services_arrivals import age_compensated, stage_ids_for_stop
from tenancy.services import get_or_create_default_island
from transit.models import DATASET_AZORESBUS, Stop

HEADERS = {'HTTP_X_ISLAND': 'sao-miguel'}
LOC_MEM_CACHE = {
    'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
}

LIST_ITEM = {'id': 'bus1', 'position': {'lat': 37.74, 'lon': -25.66},
             'status': 'ontime', 'busStatus': 'inTransitTo', 'delay': 0,
             'speed': 8.1, 'color': '2D59A9'}


def detail(due: int | None, stage_id: str = '1131') -> dict:
    circulation = {
        'sequence': 4,
        'stage': {'id': stage_id, 'name': 'FURNAS (PQ. CAMPISMO)',
                  'nameShort': '4051', 'position': {'lat': 37.77, 'lon': -25.31}},
        'departureTime': 33146, 'arrivalTime': 33146,
    }
    if due is not None:
        circulation['dueInMinutes'] = due
    return {
        'id': 'bus1', 'fleetId': '3609', 'licensePlate': '',
        'position': {'lat': 37.74, 'lon': -25.66}, 'speed': 8.1,
        'status': 'inTransitTo', 'currentStopSequence': 2,
        'route': {'id': '7', 'name': 'PONTA DELGADA - FURNAS',
                  'nameShort': '110', 'color': '2D59A9', 'isActive': True},
        'journey': {'id': '1861', 'type': 'scheduled', 'shape': 'x',
                    'circulations': [circulation]},
    }


class AgeCompensationTests(TestCase):
    def setUp(self):
        self.now = timezone.now()

    def test_a_fresh_capture_is_left_alone(self):
        stamp = (self.now - timedelta(seconds=5)).isoformat()
        self.assertEqual(age_compensated(7, stamp, self.now), 7)

    def test_a_three_minute_old_estimate_is_discounted_by_three(self):
        """dueInMinutes ticks down with the clock, so age is recoverable."""
        stamp = (self.now - timedelta(minutes=3)).isoformat()
        self.assertEqual(age_compensated(7, stamp, self.now), 4)

    def test_it_never_goes_negative(self):
        stamp = (self.now - timedelta(minutes=30)).isoformat()
        self.assertEqual(age_compensated(2, stamp, self.now), 0)

    def test_an_unparseable_stamp_leaves_the_value_alone(self):
        self.assertEqual(age_compensated(5, 'not-a-date', self.now), 5)
        self.assertEqual(age_compensated(5, '', self.now), 5)


@override_settings(CACHES=LOC_MEM_CACHE)
class StopArrivalsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.island = get_or_create_default_island()
        self.island.feature_flags = {
            **(self.island.feature_flags or {}),
            'azoresbus': {'trackingEnabled': True},
        }
        self.island.save(update_fields=['feature_flags'])

        self.stop = Stop.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS,
            name='Furnas (Parque Campismo)',
            cleaned_name='furnas parque campismo',
            latitude=37.77, longitude=-25.31,
        )
        # Two poles, one per direction, both belonging to the same stop.
        for external_id, code in (('1131', '4051'), ('1132', '4052')):
            ExternalStop.objects.create(
                island=self.island, dataset=DATASET_AZORESBUS,
                external_id=external_id, code=code,
                name='FURNAS (PQ. CAMPISMO)',
                latitude=37.77, longitude=-25.31, stop=self.stop,
            )

    def _seed_index(self, due=6, captured_at=None, stage_id='1131'):
        from azoresbus.services_route_index import _stop_index_cache_key
        cache.set(_stop_index_cache_key(self.island.key), {
            stage_id: [{
                'vehicleId': 'bus1',
                'dueInMinutes': due,
                'routeId': '7',
                'lineCode': '110',
                'journeyId': '1861',
                'capturedAt': captured_at or timezone.now().isoformat(),
            }],
        }, 600)

    def _url(self):
        return f'/api/v3/azoresbus/stops/{self.stop.pk}/arrivals'

    def test_both_poles_of_a_stop_are_searched(self):
        self.assertEqual(
            sorted(stage_ids_for_stop(self.island, self.stop.pk)), ['1131', '1132'],
        )

    @patch('azoresbus.tracking_client.requests.get')
    def test_the_number_is_re_read_rather_than_served_from_the_index(self, mock_get):
        """The index says 6; the bus is actually 2 away. Serve 2."""
        self._seed_index(due=6)
        mock_get.return_value = MagicMock(
            ok=True, status_code=200, json=lambda: detail(2), text='',
        )
        response = self.client.get(self._url(), **HEADERS)

        arrivals = response.json()['arrivals']
        self.assertEqual(len(arrivals), 1)
        self.assertEqual(arrivals[0]['dueInMinutes'], 2)
        self.assertEqual(arrivals[0]['lineCode'], '110')
        self.assertFalse(arrivals[0]['stale'])

    @patch('azoresbus.tracking_client.requests.get')
    def test_an_unreachable_vehicle_degrades_to_an_aged_estimate(self, mock_get):
        """Better a bus marked stale than a stop that claims nothing is coming."""
        self._seed_index(
            due=9, captured_at=(timezone.now() - timedelta(minutes=4)).isoformat(),
        )
        mock_get.side_effect = requests.RequestException('detail down')

        response = self.client.get(self._url(), **HEADERS)
        arrivals = response.json()['arrivals']

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(arrivals), 1)
        self.assertEqual(arrivals[0]['dueInMinutes'], 5)  # 9 minus 4 minutes of age
        self.assertTrue(arrivals[0]['stale'])

    @patch('azoresbus.tracking_client.requests.get')
    def test_a_bus_that_has_already_passed_is_dropped(self, mock_get):
        """Detail was readable and the stop is behind it -- not an arrival."""
        self._seed_index(due=1)
        mock_get.return_value = MagicMock(
            ok=True, status_code=200, json=lambda: detail(None), text='',
        )
        response = self.client.get(self._url(), **HEADERS)
        self.assertEqual(response.json()['arrivals'], [])

    @patch('azoresbus.tracking_client.requests.get')
    def test_nothing_running_is_an_empty_list_not_an_error(self, mock_get):
        response = self.client.get(self._url(), **HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['arrivals'], [])
        mock_get.assert_not_called()

    def test_a_stop_we_do_not_know_returns_nothing_rather_than_erroring(self):
        response = self.client.get('/api/v3/azoresbus/stops/999999/arrivals', **HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['arrivals'], [])

    def test_the_flag_still_gates_it(self):
        self.island.feature_flags = {'azoresbus': {'trackingEnabled': False}}
        self.island.save(update_fields=['feature_flags'])
        self._seed_index()

        response = self.client.get(self._url(), **HEADERS)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error']['code'], 'tracking_disabled')

    @patch('azoresbus.services_arrivals._refresh_deadline', return_value=1)
    @patch('azoresbus.tracking_client.requests.get')
    def test_a_slow_upstream_does_not_hold_the_request_open(
        self, mock_get, _deadline,
    ):
        """The reason this endpoint has a deadline at all.

        It holds a worker while it waits on upstream, so an unbounded wait
        queues every other request behind it -- a slow arrivals lookup was
        measurably delaying the stop page's own detail call, which is what made
        the page look like it was blocked on live data. Past the deadline we
        answer from the index instead.
        """
        import time

        self._seed_index(due=7)

        def _slow(*_args, **_kwargs):
            time.sleep(5)
            return MagicMock(ok=True, status_code=200, json=lambda: detail(2), text='')

        mock_get.side_effect = _slow

        started = time.monotonic()
        response = self.client.get(self._url(), **HEADERS)
        elapsed = time.monotonic() - started

        self.assertLess(elapsed, 4, 'the deadline should have cut the wait short')
        arrivals = response.json()['arrivals']
        self.assertEqual(len(arrivals), 1, 'the bus is still real, just not re-read')
        self.assertTrue(arrivals[0]['stale'])

    @patch('azoresbus.tracking_client.requests.get')
    def test_one_vehicle_serving_both_poles_is_listed_once(self, mock_get):
        """A bus passing outbound and inbound is still one bus coming."""
        from azoresbus.services_route_index import _stop_index_cache_key
        now = timezone.now().isoformat()
        row = {'vehicleId': 'bus1', 'routeId': '7', 'lineCode': '110',
               'journeyId': '1861', 'capturedAt': now}
        cache.set(_stop_index_cache_key(self.island.key), {
            '1131': [{**row, 'dueInMinutes': 12}],
            '1132': [{**row, 'dueInMinutes': 3}],
        }, 600)
        mock_get.return_value = MagicMock(
            ok=True, status_code=200, json=lambda: detail(3), text='',
        )

        arrivals = self.client.get(self._url(), **HEADERS).json()['arrivals']
        self.assertEqual(len(arrivals), 1)
