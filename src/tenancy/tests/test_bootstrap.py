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
