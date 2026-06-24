"""App update-check service and endpoint tests."""

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from tenancy.models import AppReleaseConfig
from tenancy.services_release import ReleaseValidationError, build_update_check
from tenancy.services import get_or_create_default_island


def _seed_release_config(island, **overrides):
    defaults = {
        'ios_current_version': '5.1.6',
        'android_current_version': '5.1.6',
        'ios_update_mode': AppReleaseConfig.UPDATE_MODE_OPTIONAL,
        'android_update_mode': AppReleaseConfig.UPDATE_MODE_REQUIRED,
        'ios_store_url': 'https://apps.apple.com/test',
        'android_store_url': 'https://play.google.com/store/apps/details?id=test',
    }
    defaults.update(overrides)
    config, _ = AppReleaseConfig.objects.update_or_create(island=island, defaults=defaults)
    for key, value in defaults.items():
        setattr(config, key, value)
    config.save()
    return config


class BuildUpdateCheckTestCase(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        _seed_release_config(self.island)

    def test_client_behind_ios(self):
        payload = build_update_check('ios', '5.1.5', island=self.island)
        self.assertTrue(payload['updateRequired'])
        self.assertEqual(payload['updateMode'], 'optional')
        self.assertEqual(payload['storeUrl'], 'https://apps.apple.com/test')
        self.assertEqual(payload['currentVersion'], '5.1.6')
        self.assertEqual(payload['clientVersion'], '5.1.5')

    def test_client_equal(self):
        payload = build_update_check('ios', '5.1.6', island=self.island)
        self.assertFalse(payload['updateRequired'])
        self.assertNotIn('updateMode', payload)
        self.assertNotIn('storeUrl', payload)

    def test_client_ahead(self):
        payload = build_update_check('android', '5.2.0', island=self.island)
        self.assertFalse(payload['updateRequired'])

    def test_android_required_mode(self):
        payload = build_update_check('android', '5.1.0', island=self.island)
        self.assertTrue(payload['updateRequired'])
        self.assertEqual(payload['updateMode'], 'required')

    def test_invalid_client_version_fails_safe(self):
        payload = build_update_check('ios', 'not-a-version', island=self.island)
        self.assertFalse(payload['updateRequired'])

    def test_unknown_platform_raises(self):
        with self.assertRaises(ReleaseValidationError):
            build_update_check('web', '5.1.6', island=self.island)

    def test_empty_version_raises(self):
        with self.assertRaises(ReleaseValidationError):
            build_update_check('ios', '', island=self.island)

    @override_settings(
        APP_RELEASE_IOS_VERSION='9.9.9',
        APP_STORE_IOS_URL='https://apps.apple.com/env-default',
    )
    def test_get_or_create_uses_env_defaults_for_new_island(self):
        island = get_or_create_default_island()
        AppReleaseConfig.objects.filter(island=island).delete()
        payload = build_update_check('ios', '1.0.0', island=island)
        self.assertTrue(payload['updateRequired'])
        self.assertEqual(payload['currentVersion'], '9.9.9')
        self.assertEqual(payload['storeUrl'], 'https://apps.apple.com/env-default')

    def test_admin_model_changes_apply_immediately(self):
        config = AppReleaseConfig.objects.get(island=self.island)
        config.ios_current_version = '5.3.0'
        config.save(update_fields=['ios_current_version'])
        payload = build_update_check('ios', '5.2.0', island=self.island)
        self.assertTrue(payload['updateRequired'])
        self.assertEqual(payload['currentVersion'], '5.3.0')


class AppUpdateCheckViewTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.island = get_or_create_default_island()
        self.island.is_live = True
        self.island.save()
        _seed_release_config(
            self.island,
            ios_current_version='5.2.0',
            android_current_version='5.2.0',
            android_update_mode=AppReleaseConfig.UPDATE_MODE_OPTIONAL,
        )
        self.headers = {'HTTP_X_ISLAND': 'sao-miguel'}

    def test_requires_island(self):
        with override_settings(DEFAULT_ISLAND_KEY='missing-island'):
            response = self.client.get('/api/v3/app/update-check?platform=ios&version=5.0.0')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], 'island_required')

    def test_valid_ios_request_behind(self):
        response = self.client.get(
            '/api/v3/app/update-check?platform=ios&version=5.0.0',
            **self.headers,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['updateRequired'])
        self.assertEqual(body['storeUrl'], 'https://apps.apple.com/test')

    def test_valid_request_current(self):
        response = self.client.get(
            '/api/v3/app/update-check?platform=ios&version=5.2.0',
            **self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['updateRequired'])

    def test_missing_version(self):
        response = self.client.get('/api/v3/app/update-check?platform=ios', **self.headers)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], 'invalid_version')

    def test_invalid_platform(self):
        response = self.client.get(
            '/api/v3/app/update-check?platform=web&version=5.0.0',
            **self.headers,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], 'invalid_platform')
