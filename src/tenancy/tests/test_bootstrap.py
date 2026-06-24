"""Bootstrap payload tests."""

from django.test import TestCase

from tenancy.bootstrap import enabled_modules, serialize_bootstrap
from tenancy.services import get_or_create_default_island
from tenancy.services_release import get_or_create_app_release_config


class BootstrapModulesTestCase(TestCase):
    def test_enabled_modules_includes_seismic_when_flag_set(self):
        island = get_or_create_default_island()
        island.feature_flags = {**island.feature_flags, 'seismic': True, 'transit': True}
        island.save(update_fields=['feature_flags'])
        modules = enabled_modules(island)
        self.assertIn('seismic', modules)

    def test_enabled_modules_omits_seismic_when_flag_false(self):
        island = get_or_create_default_island()
        flags = dict(island.feature_flags or {})
        flags['seismic'] = False
        island.feature_flags = flags
        island.save(update_fields=['feature_flags'])
        modules = enabled_modules(island)
        self.assertNotIn('seismic', modules)

    def test_enabled_modules_includes_trails_when_flag_set(self):
        island = get_or_create_default_island()
        island.feature_flags = {**island.feature_flags, 'trails': True, 'transit': True}
        island.save(update_fields=['feature_flags'])
        modules = enabled_modules(island)
        self.assertIn('trails', modules)

    def test_enabled_modules_omits_trails_when_flag_false(self):
        island = get_or_create_default_island()
        flags = dict(island.feature_flags or {})
        flags['trails'] = False
        island.feature_flags = flags
        island.save(update_fields=['feature_flags'])
        modules = enabled_modules(island)
        self.assertNotIn('trails', modules)

    def test_enabled_modules_includes_marketplace_when_flag_set(self):
        island = get_or_create_default_island()
        island.feature_flags = {**island.feature_flags, 'marketplace': True, 'transit': True}
        island.save(update_fields=['feature_flags'])
        modules = enabled_modules(island)
        self.assertIn('marketplace', modules)

    def test_enabled_modules_omits_marketplace_when_flag_false(self):
        island = get_or_create_default_island()
        flags = dict(island.feature_flags or {})
        flags['marketplace'] = False
        island.feature_flags = flags
        island.save(update_fields=['feature_flags'])
        modules = enabled_modules(island)
        self.assertNotIn('marketplace', modules)

    def test_enabled_modules_includes_traffic_when_flag_set(self):
        island = get_or_create_default_island()
        island.feature_flags = {**island.feature_flags, 'traffic': True, 'transit': True}
        island.save(update_fields=['feature_flags'])
        modules = enabled_modules(island)
        self.assertIn('traffic', modules)

    def test_enabled_modules_omits_traffic_when_flag_false(self):
        island = get_or_create_default_island()
        flags = dict(island.feature_flags or {})
        flags['traffic'] = False
        island.feature_flags = flags
        island.save(update_fields=['feature_flags'])
        modules = enabled_modules(island)
        self.assertNotIn('traffic', modules)

    def test_enabled_modules_includes_events_when_flag_set(self):
        island = get_or_create_default_island()
        island.feature_flags = {**island.feature_flags, 'events': True, 'transit': True}
        island.save(update_fields=['feature_flags'])
        modules = enabled_modules(island)
        self.assertIn('events', modules)

    def test_enabled_modules_omits_events_when_flag_false(self):
        island = get_or_create_default_island()
        flags = dict(island.feature_flags or {})
        flags['events'] = False
        island.feature_flags = flags
        island.save(update_fields=['feature_flags'])
        modules = enabled_modules(island)
        self.assertNotIn('events', modules)

    def test_enabled_modules_includes_weather_when_flag_set(self):
        island = get_or_create_default_island()
        island.feature_flags = {**island.feature_flags, 'weather': True, 'transit': True}
        island.save(update_fields=['feature_flags'])
        modules = enabled_modules(island)
        self.assertIn('weather', modules)

    def test_enabled_modules_omits_weather_when_flag_false(self):
        island = get_or_create_default_island()
        flags = dict(island.feature_flags or {})
        flags['weather'] = False
        island.feature_flags = flags
        island.save(update_fields=['feature_flags'])
        modules = enabled_modules(island)
        self.assertNotIn('weather', modules)


class BootstrapInAppReviewTestCase(TestCase):
    def test_bootstrap_in_app_review_disabled_by_default(self):
        island = get_or_create_default_island()
        payload = serialize_bootstrap(island)
        self.assertFalse(payload['inAppReviewEnabled'])
        self.assertIn('ios', payload['storeUrls'])
        self.assertIn('android', payload['storeUrls'])

    def test_bootstrap_in_app_review_enabled_when_admin_sets_flag(self):
        island = get_or_create_default_island()
        config = get_or_create_app_release_config(island)
        config.in_app_review_enabled = True
        config.save(update_fields=['in_app_review_enabled'])
        payload = serialize_bootstrap(island)
        self.assertTrue(payload['inAppReviewEnabled'])

    def test_get_or_create_app_release_config_seeds_in_app_review_disabled(self):
        island = get_or_create_default_island()
        config = get_or_create_app_release_config(island)
        self.assertFalse(config.in_app_review_enabled)
