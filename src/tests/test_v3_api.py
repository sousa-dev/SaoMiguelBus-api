"""v3 API integration tests."""

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from analytics.models import AnalyticsEvent
from tenancy.services import get_or_create_default_island


class V3APITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.island = get_or_create_default_island()
        self.island.is_live = True
        self.island.feature_flags = {**self.island.feature_flags, 'transit': True}
        self.island.save()
        self.headers = {'HTTP_X_ISLAND': 'sao-miguel'}

    def test_bootstrap(self):
        response = self.client.get('/api/v3/bootstrap', **self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['island']['key'], 'sao-miguel')
        self.assertIn('transit', response.json()['island']['enabledModules'])
        self.assertIn('consentPolicyVersion', response.json())
        self.assertIn('socialAuth', response.json())
        self.assertIn('google', response.json()['socialAuth'])
        self.assertIn('apple', response.json()['socialAuth'])
        self.assertFalse(response.json()['inAppReviewEnabled'])
        self.assertIn('storeUrls', response.json())

    def test_bootstrap_in_app_review_enabled_when_admin_sets_flag(self):
        from tenancy.services_release import get_or_create_app_release_config

        config = get_or_create_app_release_config(self.island)
        config.in_app_review_enabled = True
        config.save(update_fields=['in_app_review_enabled'])
        response = self.client.get('/api/v3/bootstrap', **self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['inAppReviewEnabled'])

    @override_settings(GOOGLE_OAUTH_CLIENT_IDS=['web-client.apps.googleusercontent.com'])
    def test_bootstrap_social_auth_google_enabled_when_client_ids_set(self):
        response = self.client.get('/api/v3/bootstrap', **self.headers)
        self.assertTrue(response.json()['socialAuth']['google'])

    @override_settings(GOOGLE_OAUTH_CLIENT_IDS=[])
    def test_bootstrap_social_auth_google_disabled_when_client_ids_empty(self):
        response = self.client.get('/api/v3/bootstrap', **self.headers)
        self.assertFalse(response.json()['socialAuth']['google'])

    @override_settings(APPLE_BUNDLE_IDS=['com.example.app'])
    def test_bootstrap_social_auth_apple_enabled_when_bundle_ids_set(self):
        response = self.client.get('/api/v3/bootstrap', **self.headers)
        self.assertTrue(response.json()['socialAuth']['apple'])

    @override_settings(APPLE_BUNDLE_IDS=[])
    def test_bootstrap_social_auth_apple_disabled_when_bundle_ids_empty(self):
        response = self.client.get('/api/v3/bootstrap', **self.headers)
        self.assertFalse(response.json()['socialAuth']['apple'])

    def test_consent_and_analytics_gated(self):
        session_id = 'test-session-abc'
        post = self.client.post(
            '/api/v3/consent/',
            {
                'session_id': session_id,
                'purposes': {
                    'strictly_necessary': True,
                    'analytics': True,
                    'ads': False,
                    'personalization': False,
                },
            },
            format='json',
            **self.headers,
        )
        self.assertEqual(post.status_code, 201)

        events = self.client.post(
            '/api/v3/analytics/events',
            {
                'session_id': session_id,
                'platform': 'ios',
                'locale': 'pt',
                'events': [
                    {
                        'module': 'transit',
                        'event_type': 'search',
                        'properties': {'origin': 'Ponta Delgada', 'destination': 'Ribeira Grande'},
                    }
                ],
            },
            format='json',
            **self.headers,
        )
        self.assertEqual(events.status_code, 200)
        self.assertEqual(events.json()['accepted'], 1)
        self.assertEqual(AnalyticsEvent.objects.count(), 1)

    def test_analytics_dropped_without_consent(self):
        events = self.client.post(
            '/api/v3/analytics/events',
            {
                'session_id': 'no-consent-session',
                'platform': 'ios',
                'events': [{'module': 'transit', 'event_type': 'load', 'properties': {}}],
            },
            format='json',
            **self.headers,
        )
        self.assertEqual(events.status_code, 200)
        self.assertEqual(events.json()['accepted'], 0)
        self.assertEqual(AnalyticsEvent.objects.count(), 0)
