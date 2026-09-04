from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from azoresbus.apns import ApnsError
from azoresbus.models import LiveActivityRegistration
from azoresbus.tasks import PUSH_LOCK_KEY, push_live_activities_task
from tenancy.services import get_or_create_default_island

LOC_MEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}


def _live_row(trip_id: int, due_in_minutes: int = 4) -> dict:
    return {
        'tripId': trip_id,
        'state': 'live',
        'vehicle': {
            'id': 'v1', 'position': {'lat': 37.8, 'lon': -25.6}, 'delaySeconds': 60,
            'speed': 20, 'status': 'inTransitTo', 'currentStopSequence': 2,
            'nextStop': {'sequence': 3, 'name': 'Pico da Pedra', 'stopId': 9, 'dueInMinutes': due_in_minutes},
            'upcomingStops': [{'sequence': 3, 'name': 'Pico da Pedra', 'stopId': 9, 'dueInMinutes': due_in_minutes}],
            'capturedAt': timezone.now().isoformat(), 'stale': False,
        },
    }


@override_settings(CACHES=LOC_MEM_CACHE)
class PushLiveActivitiesTaskTests(TestCase):
    def setUp(self):
        cache.clear()
        self.island = get_or_create_default_island()
        now = timezone.now()
        self.registration = LiveActivityRegistration.objects.create(
            island=self.island,
            push_token='token-a',
            environment='development',
            activity_key='t1',
            legs=[{
                'tripId': 1936,
                'startsAt': (now - timedelta(minutes=10)).isoformat(),
                'endsAt': (now + timedelta(minutes=30)).isoformat(),
            }],
            expires_at=now + timedelta(hours=1),
        )

    @patch('azoresbus.apns.push_live_activity')
    @patch('azoresbus.services_trip_live.live_for_trips')
    def test_pushes_a_live_snapshot_and_records_last_pushed_at(self, mock_live_for_trips, mock_push):
        mock_live_for_trips.return_value = [_live_row(1936)]

        result = push_live_activities_task()

        self.assertEqual(result['pushed'], 1)
        self.assertEqual(result['ended'], 0)
        self.assertEqual(result['failed'], 0)
        mock_push.assert_called_once()
        token, environment, payload = mock_push.call_args[0]
        self.assertEqual(token, 'token-a')
        self.assertEqual(environment, 'development')
        self.assertEqual(payload['aps']['event'], 'update')
        self.assertEqual(payload['aps']['content-state']['nextStopName'], 'Pico da Pedra')

        self.registration.refresh_from_db()
        self.assertIsNotNone(self.registration.last_pushed_at)
        self.assertIsNone(self.registration.ended_at)

    @patch('azoresbus.apns.push_live_activity')
    @patch('azoresbus.services_trip_live.live_for_trips')
    def test_sends_an_end_event_and_ends_the_registration_once_finished(
        self, mock_live_for_trips, mock_push,
    ):
        past = timezone.now() - timedelta(hours=1)
        self.registration.legs = [{
            'tripId': 1936,
            'startsAt': (past - timedelta(minutes=44)).isoformat(),
            'endsAt': past.isoformat(),
        }]
        self.registration.save(update_fields=['legs'])
        mock_live_for_trips.return_value = []

        result = push_live_activities_task()

        self.assertEqual(result['ended'], 1)
        mock_push.assert_called_once()
        payload = mock_push.call_args[0][2]
        self.assertEqual(payload['aps']['event'], 'end')
        self.assertIn('dismissal-date', payload['aps'])

        self.registration.refresh_from_db()
        self.assertIsNotNone(self.registration.ended_at)

    @patch('azoresbus.apns.push_live_activity')
    @patch('azoresbus.services_trip_live.live_for_trips')
    def test_a_terminal_apns_error_ends_the_registration(self, mock_live_for_trips, mock_push):
        mock_live_for_trips.return_value = [_live_row(1936)]
        mock_push.side_effect = ApnsError('apns 410: Unregistered', terminal=True)

        result = push_live_activities_task()

        self.assertEqual(result['failed'], 1)
        self.registration.refresh_from_db()
        self.assertIsNotNone(self.registration.ended_at)
        self.assertEqual(self.registration.failure_count, 1)

    @patch('azoresbus.apns.push_live_activity')
    @patch('azoresbus.services_trip_live.live_for_trips')
    def test_a_non_terminal_apns_error_leaves_the_registration_alive(
        self, mock_live_for_trips, mock_push,
    ):
        mock_live_for_trips.return_value = [_live_row(1936)]
        mock_push.side_effect = ApnsError('apns request failed: timeout', terminal=False)

        push_live_activities_task()

        self.registration.refresh_from_db()
        self.assertIsNone(self.registration.ended_at)
        self.assertEqual(self.registration.failure_count, 1)

    def test_a_stuck_run_is_skipped_rather_than_overlapped(self):
        cache.set(PUSH_LOCK_KEY, 'held', 50)
        result = push_live_activities_task()
        self.assertEqual(result['status'], 'skipped')

    @patch('azoresbus.apns.push_live_activity')
    @patch('azoresbus.services_trip_live.live_for_trips')
    def test_an_already_ended_registration_is_never_touched(self, mock_live_for_trips, mock_push):
        self.registration.ended_at = timezone.now()
        self.registration.save(update_fields=['ended_at'])

        push_live_activities_task()

        mock_live_for_trips.assert_not_called()
        mock_push.assert_not_called()
