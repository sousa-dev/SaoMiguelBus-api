"""`GET /api/v3/transit/live-counts` -- the cached, vendor-free hub endpoint.

Owner's rule, in four parts:
    a recorded count/outage is served as-is, no vendor call
    a recorded 0 or outage triggers ONE refresh, but only 06:00-18:59 Azores
      time, and at most once per 5 minutes per operator
    a COMPLETELY MISSING record (first deploy, a cache flush) refreshes
      regardless of the clock -- MiniBus has no background job keeping it
      warm the way AzoresBus's route-index sweep does, so waiting for
      morning would mean an all-night blank hub for no reason
    a refresh failure is reported as `unavailable`, never a 5xx
"""

from __future__ import annotations

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from azoresbus.tracking_client import AzoresbusTrackingError
from minibus.tracking_client import MinibusTrackingError
from shared.live_counts import (
    attempt_key,
    count_key,
    mark_refresh_attempt,
    record_live_count,
    record_live_outage,
)
from tenancy.services import get_or_create_default_island

HEADERS = {'HTTP_X_ISLAND': 'sao-miguel'}
URL = '/api/v3/transit/live-counts'


class LiveCountsApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.island = get_or_create_default_island()
        self._flag_azoresbus(True)

    def tearDown(self):
        cache.clear()

    def _flag_azoresbus(self, enabled: bool):
        self.island.feature_flags = {
            **(self.island.feature_flags or {}),
            'azoresbus': {'trackingEnabled': enabled},
        }
        self.island.save(update_fields=['feature_flags'])

    def test_requires_island(self):
        # The tenancy middleware always binds SOME island (the default),
        # even with no `X-Island` header -- `_require_island` only fires
        # when even the default key resolves to nothing, same trick the
        # minibus health test uses.
        with override_settings(DEFAULT_ISLAND_KEY='missing-island'):
            response = self.client.get(URL)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], 'island_required')

    @patch('shared.live_counts.is_refresh_daytime', return_value=False)
    @patch('minibus.services_tracking.fetch_fleet_locations')
    @patch('azoresbus.services_tracking.fetch_fleet_locations')
    def test_no_records_at_night_still_refreshes_once_per_operator(
        self, mock_azoresbus_fetch, mock_minibus_fetch, _mock_daytime,
    ):
        """A completely missing record ignores the clock (unlike a recorded 0
        or outage): right after a deploy or a cache flush, MiniBus has no
        background job to keep it warm on its own, so this is the only path
        that lets it recover before the next daytime hub visit."""
        mock_azoresbus_fetch.return_value = []
        mock_minibus_fetch.return_value = [{'id': 'a', 'status': 'ontime'}]

        response = self.client.get(URL, **HEADERS)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['azoresbus'], {'status': 'ok', 'vehicles': 0, 'recordedAt': body['azoresbus']['recordedAt']})
        self.assertEqual(body['minibus']['status'], 'ok')
        self.assertEqual(body['minibus']['vehicles'], 1)
        mock_azoresbus_fetch.assert_called_once()
        mock_minibus_fetch.assert_called_once()

    @patch('shared.live_counts.is_refresh_daytime', return_value=False)
    @patch('minibus.services_tracking.fetch_fleet_locations')
    @patch('azoresbus.services_tracking.fetch_fleet_locations')
    def test_second_request_at_night_after_the_first_refresh_does_not_refresh_again(
        self, mock_azoresbus_fetch, mock_minibus_fetch, _mock_daytime,
    ):
        mock_azoresbus_fetch.return_value = []
        mock_minibus_fetch.return_value = []

        self.client.get(URL, **HEADERS)
        self.client.get(URL, **HEADERS)

        mock_azoresbus_fetch.assert_called_once()
        mock_minibus_fetch.assert_called_once()

    @patch('shared.live_counts.is_refresh_daytime', return_value=True)
    @patch('minibus.services_tracking.fetch_fleet_locations')
    @patch('azoresbus.services_tracking.fetch_fleet_locations')
    def test_no_records_in_daytime_triggers_one_refresh_per_operator(
        self, mock_azoresbus_fetch, mock_minibus_fetch, _mock_daytime,
    ):
        mock_azoresbus_fetch.return_value = [{'id': '1', 'position': {'lat': 0, 'lon': 0}, 'status': 'ontime', 'color': 'EC6E00'}]
        mock_minibus_fetch.return_value = [{'id': 'a', 'status': 'ontime'}, {'id': 'b', 'status': 'ontime'}]

        response = self.client.get(URL, **HEADERS)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['azoresbus']['status'], 'ok')
        self.assertEqual(body['azoresbus']['vehicles'], 1)
        self.assertEqual(body['minibus']['status'], 'ok')
        self.assertEqual(body['minibus']['vehicles'], 2)
        mock_azoresbus_fetch.assert_called_once()
        mock_minibus_fetch.assert_called_once()
        self.assertIsNotNone(cache.get(attempt_key('azoresbus', self.island.key)))
        self.assertIsNotNone(cache.get(attempt_key('minibus', self.island.key)))

    @patch('shared.live_counts.is_refresh_daytime', return_value=True)
    @patch('minibus.services_tracking.fetch_fleet_locations')
    @patch('azoresbus.services_tracking.fetch_fleet_locations')
    def test_second_request_within_five_minutes_does_not_refresh_again(
        self, mock_azoresbus_fetch, mock_minibus_fetch, _mock_daytime,
    ):
        mock_azoresbus_fetch.return_value = []
        mock_minibus_fetch.return_value = []

        self.client.get(URL, **HEADERS)
        self.client.get(URL, **HEADERS)

        mock_azoresbus_fetch.assert_called_once()
        mock_minibus_fetch.assert_called_once()

    @patch('shared.live_counts.is_refresh_daytime', return_value=True)
    @patch('minibus.services_tracking.fetch_fleet_locations')
    @patch('azoresbus.services_tracking.fetch_fleet_locations')
    def test_recorded_nonzero_count_is_served_without_vendor_calls(
        self, mock_azoresbus_fetch, mock_minibus_fetch, _mock_daytime,
    ):
        from django.utils import timezone

        record_live_count('azoresbus', self.island.key, 7, fetched_at=timezone.now())
        record_live_count('minibus', self.island.key, 3, fetched_at=timezone.now())

        response = self.client.get(URL, **HEADERS)

        body = response.json()
        self.assertEqual(body['azoresbus']['vehicles'], 7)
        self.assertEqual(body['minibus']['vehicles'], 3)
        mock_azoresbus_fetch.assert_not_called()
        mock_minibus_fetch.assert_not_called()

    @patch('shared.live_counts.is_refresh_daytime', return_value=True)
    @patch('azoresbus.services_tracking.fetch_fleet_locations')
    def test_recorded_zero_in_daytime_refreshes_once(self, mock_fetch, _mock_daytime):
        from django.utils import timezone

        record_live_count('azoresbus', self.island.key, 0, fetched_at=timezone.now())
        mock_fetch.return_value = [
            {'id': '1', 'position': {'lat': 0, 'lon': 0}, 'status': 'ontime', 'color': 'EC6E00'},
            {'id': '2', 'position': {'lat': 0, 'lon': 0}, 'status': 'ontime', 'color': 'EC6E00'},
        ]

        response = self.client.get(URL, **HEADERS)

        self.assertEqual(response.json()['azoresbus']['vehicles'], 2)
        mock_fetch.assert_called_once()

    @patch('shared.live_counts.is_refresh_daytime', return_value=False)
    @patch('azoresbus.services_tracking.fetch_fleet_locations')
    def test_recorded_zero_at_night_is_served_as_is(self, mock_fetch, _mock_daytime):
        from django.utils import timezone

        record_live_count('azoresbus', self.island.key, 0, fetched_at=timezone.now())

        response = self.client.get(URL, **HEADERS)

        self.assertEqual(response.json()['azoresbus'], {
            'status': 'ok', 'vehicles': 0,
            'recordedAt': cache.get(count_key('azoresbus', self.island.key))['recordedAt'],
        })
        mock_fetch.assert_not_called()

    @patch('shared.live_counts.is_refresh_daytime', return_value=True)
    @patch('azoresbus.services_tracking.fetch_fleet_locations')
    def test_recorded_outage_in_daytime_refreshes_once(self, mock_fetch, _mock_daytime):
        record_live_outage('azoresbus', self.island.key)
        mock_fetch.return_value = [
            {'id': '1', 'position': {'lat': 0, 'lon': 0}, 'status': 'ontime', 'color': 'EC6E00'},
        ]

        response = self.client.get(URL, **HEADERS)

        self.assertEqual(response.json()['azoresbus']['status'], 'ok')
        self.assertEqual(response.json()['azoresbus']['vehicles'], 1)
        mock_fetch.assert_called_once()

    @patch('shared.live_counts.is_refresh_daytime', return_value=True)
    @patch('azoresbus.services_tracking.fetch_fleet_locations')
    def test_refresh_failure_is_reported_as_unavailable_with_200(self, mock_fetch, _mock_daytime):
        mock_fetch.side_effect = AzoresbusTrackingError('down')

        response = self.client.get(URL, **HEADERS)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['azoresbus']['status'], 'unavailable')
        self.assertIsNotNone(cache.get(attempt_key('azoresbus', self.island.key)))

    @patch('shared.live_counts.is_refresh_daytime', return_value=True)
    @patch('minibus.services_tracking.fetch_fleet_locations')
    def test_minibus_refresh_failure_is_reported_as_unavailable_with_200(self, mock_fetch, _mock_daytime):
        mock_fetch.side_effect = MinibusTrackingError('down')

        response = self.client.get(URL, **HEADERS)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['minibus']['status'], 'unavailable')

    @patch('shared.live_counts.is_refresh_daytime', return_value=True)
    @patch('azoresbus.services_tracking.fetch_fleet_locations')
    def test_azoresbus_flag_off_is_disabled_and_never_refreshes(self, mock_fetch, _mock_daytime):
        self._flag_azoresbus(False)

        response = self.client.get(URL, **HEADERS)

        self.assertEqual(response.json()['azoresbus'], {'status': 'disabled', 'vehicles': None, 'recordedAt': None})
        mock_fetch.assert_not_called()

    @patch('transit.api_v3._minibus_installed', return_value=False)
    def test_minibus_null_when_app_not_installed(self, _mock_installed):
        response = self.client.get(URL, **HEADERS)

        self.assertIsNone(response.json()['minibus'])

    @patch.dict('os.environ', {'LIVE_COUNT_TTL': '60'})
    @patch('shared.live_counts.is_refresh_daytime', return_value=False)
    @patch('azoresbus.services_tracking.fetch_fleet_locations')
    def test_expired_record_reads_as_missing_and_refreshes_even_at_night(
        self, mock_fetch, _mock_daytime,
    ):
        """An expired record and a genuinely absent one must behave
        identically -- `read_live_count` already drops it, so this is really
        exercising the same "no record" path as a fresh deploy, just reached
        by staleness instead of a cold cache."""
        from datetime import timedelta

        from django.utils import timezone

        record_live_count('azoresbus', self.island.key, 9, fetched_at=timezone.now())
        envelope = cache.get(count_key('azoresbus', self.island.key))
        envelope['recordedAt'] = (timezone.now() - timedelta(seconds=61)).isoformat()
        cache.set(count_key('azoresbus', self.island.key), envelope, 3600)
        mock_fetch.return_value = [
            {'id': '1', 'position': {'lat': 0, 'lon': 0}, 'status': 'ontime', 'color': 'EC6E00'},
        ]

        response = self.client.get(URL, **HEADERS)

        self.assertEqual(response.json()['azoresbus']['status'], 'ok')
        self.assertEqual(response.json()['azoresbus']['vehicles'], 1)
        mock_fetch.assert_called_once()

    @patch.dict('os.environ', {'LIVE_COUNT_TTL': '60'})
    @patch('shared.live_counts.is_refresh_daytime', return_value=False)
    @patch('azoresbus.services_tracking.fetch_fleet_locations')
    def test_expired_record_stays_unknown_once_the_five_minute_window_is_spent(
        self, mock_fetch, _mock_daytime,
    ):
        from datetime import timedelta

        from django.utils import timezone

        record_live_count('azoresbus', self.island.key, 9, fetched_at=timezone.now())
        envelope = cache.get(count_key('azoresbus', self.island.key))
        envelope['recordedAt'] = (timezone.now() - timedelta(seconds=61)).isoformat()
        cache.set(count_key('azoresbus', self.island.key), envelope, 3600)
        # Someone else's request already spent this operator's 5-minute window.
        mark_refresh_attempt('azoresbus', self.island.key)

        response = self.client.get(URL, **HEADERS)

        self.assertEqual(response.json()['azoresbus']['status'], 'unknown')
        mock_fetch.assert_not_called()

    @patch('shared.live_counts.is_refresh_daytime', return_value=True)
    @patch('azoresbus.services_tracking.fetch_fleet_locations')
    def test_response_reports_the_configured_ttl(self, mock_fetch, _mock_daytime):
        mock_fetch.return_value = []

        response = self.client.get(URL, **HEADERS)

        self.assertEqual(response.json()['ttlSeconds'], 1800)
