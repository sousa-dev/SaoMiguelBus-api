"""One island's upstream failure must not cost the others their forecast cache.

Adding the Madeira tenants made this reachable: Island.Meta.ordering is by name, so
'Madeira' (53 parishes) is refreshed *before* 'São Miguel'. With no per-island guard, one
Open-Meteo error on the Madeira batch aborted the beat task and São Miguel's cache — the
shipped product's — silently went unwarmed for the hour.
"""
from unittest.mock import patch

from django.test import TestCase

from tenancy.models import Island
from weather.tasks import refresh_forecasts_task


class RefreshForecastsIsolationTests(TestCase):
    def setUp(self):
        self.calls = []
        for key, name in (('madeira', 'Madeira'), ('sao-miguel', 'São Miguel')):
            Island.objects.update_or_create(
                key=key, defaults={**Island.default_sao_miguel(), 'key': key,
                                   'name': name, 'is_live': True})
        self.assertLess('Madeira', 'São Miguel', 'ordering assumption')

    def _refresh(self, island):
        self.calls.append(island.key)
        if island.key == 'madeira':
            raise RuntimeError('open-meteo is down')
        return 7

    def test_a_failing_island_does_not_stop_the_rest(self):
        with patch('weather.services.refresh_all_parishes', side_effect=self._refresh):
            result = refresh_forecasts_task()
        self.assertIn('sao-miguel', self.calls)
        self.assertEqual(result['refreshed'].get('sao-miguel'), 7)
        self.assertIn('madeira', result.get('failed', {}))
