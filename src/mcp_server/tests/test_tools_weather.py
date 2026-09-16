"""Tests for the weather MCP tools."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from tenancy.services import for_island, get_or_create_default_island
from weather.models import Parish
from weather.open_meteo_client import OpenMeteoError
from mcp_server.tools.weather import _parish_impl, _parishes_impl


class WeatherToolsTestCase(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        with for_island(self.island):
            self.parish = Parish.objects.create(
                island=self.island, name='Ponta Delgada', slug='ponta-delgada',
                concelho='Ponta Delgada', latitude=37.7411, longitude=-25.6756,
            )

    def test_parishes_unavailable_maps_to_weather_unavailable(self):
        with patch(
            'weather.services.list_parish_weather',
            side_effect=OpenMeteoError('upstream down'),
        ):
            with for_island(self.island):
                result = _parishes_impl(self.island)
        self.assertEqual(result['error']['code'], 'weather_unavailable')

    def test_parish_unknown_slug_is_not_found(self):
        with for_island(self.island):
            result = _parish_impl(self.island, 'does-not-exist')
        self.assertEqual(result['error']['code'], 'not_found')

    def test_parish_upstream_error_maps_to_weather_unavailable(self):
        with patch(
            'weather.services.get_parish_weather',
            side_effect=OpenMeteoError('upstream down'),
        ):
            with for_island(self.island):
                result = _parish_impl(self.island, self.parish.slug)
        self.assertEqual(result['error']['code'], 'weather_unavailable')
