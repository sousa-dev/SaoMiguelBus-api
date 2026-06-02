"""Bootstrap payload tests."""

from django.test import TestCase

from tenancy.bootstrap import enabled_modules
from tenancy.services import get_or_create_default_island


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
