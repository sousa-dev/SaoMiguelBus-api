from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from azoresbus.models import LiveActivityRegistration
from tenancy.services import get_or_create_default_island

HEADERS = {'HTTP_X_ISLAND': 'sao-miguel'}
LOC_MEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}

VALID_BODY = {
    'pushToken': 'abc123',
    'environment': 'development',
    'activityKey': 't1',
    'legs': [
        {'tripId': 1936, 'startsAt': '2026-09-02T21:15:00+00:00', 'endsAt': '2026-09-02T21:59:00+00:00'},
    ],
    'expiresAt': '2026-09-02T22:30:00+00:00',
}


@override_settings(CACHES=LOC_MEM_CACHE)
class LiveActivityRegisterTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.island = get_or_create_default_island()
        self.island.feature_flags = {
            **(self.island.feature_flags or {}),
            'azoresbus': {'trackingEnabled': True},
        }
        self.island.save(update_fields=['feature_flags'])

    def test_register_creates_one_row(self):
        response = self.client.post(
            '/api/v3/azoresbus/live-activities', VALID_BODY, format='json', **HEADERS,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {'registered': True})
        self.assertEqual(LiveActivityRegistration.objects.count(), 1)
        row = LiveActivityRegistration.objects.get()
        self.assertEqual(row.push_token, 'abc123')
        self.assertEqual(row.environment, 'development')
        self.assertEqual(row.activity_key, 't1')
        self.assertEqual(row.legs, [
            {'tripId': 1936, 'startsAt': '2026-09-02T21:15:00+00:00', 'endsAt': '2026-09-02T21:59:00+00:00'},
        ])
        self.assertIsNone(row.ended_at)

    def test_reregistering_the_same_token_updates_rather_than_duplicates(self):
        self.client.post('/api/v3/azoresbus/live-activities', VALID_BODY, format='json', **HEADERS)
        second = {**VALID_BODY, 'activityKey': 't2'}
        response = self.client.post(
            '/api/v3/azoresbus/live-activities', second, format='json', **HEADERS,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(LiveActivityRegistration.objects.count(), 1)
        self.assertEqual(LiveActivityRegistration.objects.get().activity_key, 't2')

    def test_reregistering_clears_a_previous_end(self):
        self.client.post('/api/v3/azoresbus/live-activities', VALID_BODY, format='json', **HEADERS)
        self.client.delete('/api/v3/azoresbus/live-activities/abc123', **HEADERS)
        self.assertIsNotNone(LiveActivityRegistration.objects.get().ended_at)

        self.client.post('/api/v3/azoresbus/live-activities', VALID_BODY, format='json', **HEADERS)
        self.assertIsNone(LiveActivityRegistration.objects.get().ended_at)

    def test_malformed_legs_is_a_400_not_a_500(self):
        bad = {**VALID_BODY, 'legs': 'not-a-list'}
        response = self.client.post('/api/v3/azoresbus/live-activities', bad, format='json', **HEADERS)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], 'invalid_request')
        self.assertEqual(LiveActivityRegistration.objects.count(), 0)

    def test_missing_push_token_is_a_400(self):
        bad = {**VALID_BODY, 'pushToken': ''}
        response = self.client.post('/api/v3/azoresbus/live-activities', bad, format='json', **HEADERS)
        self.assertEqual(response.status_code, 400)

    def test_invalid_environment_is_a_400(self):
        bad = {**VALID_BODY, 'environment': 'staging'}
        response = self.client.post('/api/v3/azoresbus/live-activities', bad, format='json', **HEADERS)
        self.assertEqual(response.status_code, 400)

    def test_503_when_tracking_disabled(self):
        self.island.feature_flags = {'azoresbus': {'trackingEnabled': False}}
        self.island.save(update_fields=['feature_flags'])
        response = self.client.post(
            '/api/v3/azoresbus/live-activities', VALID_BODY, format='json', **HEADERS,
        )
        self.assertEqual(response.status_code, 503)


@override_settings(CACHES=LOC_MEM_CACHE)
class LiveActivityUnregisterTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.island = get_or_create_default_island()
        self.island.feature_flags = {
            **(self.island.feature_flags or {}),
            'azoresbus': {'trackingEnabled': True},
        }
        self.island.save(update_fields=['feature_flags'])
        self.client.post('/api/v3/azoresbus/live-activities', VALID_BODY, format='json', **HEADERS)

    def test_unregister_marks_ended_rather_than_deleting(self):
        response = self.client.delete('/api/v3/azoresbus/live-activities/abc123', **HEADERS)
        self.assertEqual(response.status_code, 204)
        row = LiveActivityRegistration.objects.get()
        self.assertIsNotNone(row.ended_at)

    def test_unregistering_an_unknown_token_is_not_an_error(self):
        response = self.client.delete('/api/v3/azoresbus/live-activities/never-seen', **HEADERS)
        self.assertEqual(response.status_code, 204)

    def test_unregistering_twice_is_not_an_error(self):
        self.client.delete('/api/v3/azoresbus/live-activities/abc123', **HEADERS)
        response = self.client.delete('/api/v3/azoresbus/live-activities/abc123', **HEADERS)
        self.assertEqual(response.status_code, 204)

    def test_503_when_tracking_disabled(self):
        self.island.feature_flags = {'azoresbus': {'trackingEnabled': False}}
        self.island.save(update_fields=['feature_flags'])
        response = self.client.delete('/api/v3/azoresbus/live-activities/abc123', **HEADERS)
        self.assertEqual(response.status_code, 503)
