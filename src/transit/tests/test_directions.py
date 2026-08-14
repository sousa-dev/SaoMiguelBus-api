"""Directions service tests."""

from __future__ import annotations

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from tenancy.services import get_or_create_default_island
from transit.services.directions_cache import build_cache_key, get_cached_directions, set_cached_directions
from transit.services.directions_v3 import fetch_gmaps_directions, get_directions_v3, resolve_departure_timestamp


class DirectionsServiceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.island = get_or_create_default_island()
        self.island.feature_flags = {**(self.island.feature_flags or {}), 'maps': True}
        self.island.save(update_fields=['feature_flags'])

    def test_maps_disabled_returns_400(self):
        self.island.feature_flags = {'maps': False}
        payload, status_code = fetch_gmaps_directions(
            island=self.island,
            origin='Ponta Delgada',
            destination='Ribeira Grande',
        )
        self.assertEqual(status_code, 400)
        self.assertIn('error', payload)

    def test_missing_origin_destination_returns_400(self):
        payload, status_code = fetch_gmaps_directions(
            island=self.island,
            origin='',
            destination='Ribeira Grande',
        )
        self.assertEqual(status_code, 400)

    @override_settings(GOOGLE_MAPS_API_KEY='test-key')
    @patch('transit.services.directions_v3.requests.get')
    def test_get_directions_v3_caches_success(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            'routes': [{'summary': 'Bus 208', 'legs': []}],
        }

        payload1, status1, hit1 = get_directions_v3(
            island=self.island,
            origin='Cache Test Origin',
            destination='Cache Test Destination',
            day='weekday',
            start='08:00',
        )
        payload2, status2, hit2 = get_directions_v3(
            island=self.island,
            origin='Cache Test Origin',
            destination='Cache Test Destination',
            day='weekday',
            start='08:00',
        )

        self.assertEqual(status1, 200)
        self.assertFalse(hit1)
        self.assertEqual(status2, 200)
        self.assertTrue(hit2)
        self.assertEqual(payload1['routes'][0]['summary'], payload2['routes'][0]['summary'])
        self.assertEqual(mock_get.call_count, 1)

    @override_settings(GOOGLE_MAPS_API_KEY='')
    def test_missing_maps_key_returns_503(self):
        payload, status_code = fetch_gmaps_directions(
            island=self.island,
            origin='A',
            destination='B',
        )
        self.assertEqual(status_code, 503)
        self.assertEqual(payload, {'warning': 'NA'})

    def test_cache_key_is_stable(self):
        key_a = build_cache_key(
            island_key='sao-miguel',
            origin='Ponta Delgada',
            destination='Ribeira Grande',
            day='weekday',
            start='08:00',
            locale='pt',
            dataset='legacy',
        )
        key_b = build_cache_key(
            island_key='sao-miguel',
            origin='ponta delgada',
            destination='ribeira grande',
            day='weekday',
            start='08:00',
            locale='pt',
            dataset='legacy',
        )
        self.assertEqual(key_a, key_b)

    def test_resolve_departure_timestamp_from_date(self):
        ts = resolve_departure_timestamp(
            island=self.island,
            date='2030-06-03',
            start='09:30',
        )
        self.assertIsInstance(ts, int)
        self.assertGreater(ts, 0)

    def test_cache_round_trip(self):
        key = 'test:directions:roundtrip'
        set_cached_directions(key, {'routes': []})
        self.assertEqual(get_cached_directions(key), {'routes': []})
