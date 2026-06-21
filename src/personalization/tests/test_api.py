"""Personalization v3 API tests."""

from django.test import TestCase
from rest_framework.test import APIClient

from consent.services import hash_session_id
from personalization.models import PersonalizationProfile
from tenancy.services import get_or_create_default_island


class PersonalizationAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.island = get_or_create_default_island()
        self.island.is_live = True
        self.island.save()
        self.headers = {'HTTP_X_ISLAND': 'sao-miguel'}
        self.session_id = 'personalization-test-session'

    def _session_hash(self) -> str:
        return hash_session_id(self.session_id, 'sao-miguel')

    def test_post_and_get_profile(self):
        post = self.client.post(
            '/api/v3/personalization/',
            {
                'session_id': self.session_id,
                'user_type': 'tourist',
                'interests': ['trails', 'events'],
                'home_municipality': 'ponta-delgada',
            },
            format='json',
            **self.headers,
        )
        self.assertEqual(post.status_code, 201)
        self.assertEqual(post.json()['user_type'], 'tourist')
        self.assertEqual(post.json()['interests'], ['trails', 'events'])
        self.assertEqual(post.json()['home_municipality'], 'ponta-delgada')
        self.assertEqual(PersonalizationProfile.objects.count(), 1)

        get = self.client.get(
            f'/api/v3/personalization/?session_id={self.session_id}',
            **self.headers,
        )
        self.assertEqual(get.status_code, 200)
        self.assertEqual(get.json()['user_type'], 'tourist')
        self.assertEqual(get.json()['interests'], ['trails', 'events'])

    def test_get_requires_session_id(self):
        response = self.client.get('/api/v3/personalization/', **self.headers)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], 'session_required')

    def test_post_invalid_user_type(self):
        response = self.client.post(
            '/api/v3/personalization/',
            {
                'session_id': self.session_id,
                'user_type': 'invalid',
                'interests': [],
            },
            format='json',
            **self.headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_post_invalid_interest(self):
        response = self.client.post(
            '/api/v3/personalization/',
            {
                'session_id': self.session_id,
                'user_type': 'tourist',
                'interests': ['not-a-module'],
            },
            format='json',
            **self.headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_upsert_updates_existing_profile(self):
        self.client.post(
            '/api/v3/personalization/',
            {
                'session_id': self.session_id,
                'user_type': 'tourist',
                'interests': ['trails'],
                'home_municipality': 'ponta-delgada',
            },
            format='json',
            **self.headers,
        )
        self.client.post(
            '/api/v3/personalization/',
            {
                'session_id': self.session_id,
                'user_type': 'resident',
                'interests': ['transit', 'news'],
                'home_municipality': 'ribeira-grande',
            },
            format='json',
            **self.headers,
        )
        self.assertEqual(PersonalizationProfile.objects.count(), 1)
        profile = PersonalizationProfile.objects.get()
        self.assertEqual(profile.user_type, 'resident')
        self.assertEqual(profile.interests, ['transit', 'news'])

    def test_dsar_export_includes_personalization(self):
        self.client.post(
            '/api/v3/personalization/',
            {
                'session_id': self.session_id,
                'user_type': 'newcomer',
                'interests': ['marketplace'],
                'home_municipality': 'lagoa',
            },
            format='json',
            **self.headers,
        )
        export = self.client.post(
            '/api/v3/privacy/dsar/export',
            {'session_id': self.session_id},
            format='json',
            **self.headers,
        )
        self.assertEqual(export.status_code, 200)
        payload = export.json()
        self.assertIn('personalization', payload)
        self.assertEqual(len(payload['personalization']), 1)
        self.assertEqual(payload['personalization'][0]['user_type'], 'newcomer')

    def test_dsar_delete_removes_personalization(self):
        self.client.post(
            '/api/v3/personalization/',
            {
                'session_id': self.session_id,
                'user_type': 'tourist',
                'interests': ['events'],
            },
            format='json',
            **self.headers,
        )
        self.assertEqual(PersonalizationProfile.objects.count(), 1)

        delete = self.client.post(
            '/api/v3/privacy/dsar/delete',
            {'session_id': self.session_id},
            format='json',
            **self.headers,
        )
        self.assertEqual(delete.status_code, 200)
        self.assertEqual(delete.json()['personalization_profiles_deleted'], 1)
        self.assertEqual(PersonalizationProfile.objects.count(), 0)
