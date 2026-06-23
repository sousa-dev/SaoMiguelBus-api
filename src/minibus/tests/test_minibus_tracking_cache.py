"""Tests for minibus live tracking cache service."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from minibus.services_tracking import (
    CacheMeta,
    get_fleet_tracking,
    get_tracking_config,
    get_vehicle_tracking,
)
from minibus.tracking_client import MinibusTrackingError
from tenancy.services import get_or_create_default_island


class TrackingConfigTestCase(TestCase):
    @patch.dict('os.environ', {'MINIBUS_TRACKING_CACHE_TTL': '5'})
    def test_cache_ttl_from_env(self):
        config = get_tracking_config()
        self.assertEqual(config['cache_ttl'], 5)
        self.assertEqual(config['cache_max_age_seconds'], 5)

    @patch.dict('os.environ', {'MINIBUS_TRACKING_CACHE_TTL': '0'})
    def test_cache_ttl_clamped_to_minimum(self):
        config = get_tracking_config()
        self.assertEqual(config['cache_ttl'], 1)

    @patch.dict('os.environ', {'MINIBUS_TRACKING_CACHE_TTL': '9999'})
    def test_cache_ttl_clamped_to_maximum(self):
        config = get_tracking_config()
        self.assertEqual(config['cache_ttl'], 300)


class FleetTrackingCacheTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.island = get_or_create_default_island()
        self.fleet_payload = [{'id': '11010939', 'status': 'ontime'}]

    @patch.dict('os.environ', {'MINIBUS_TRACKING_CACHE_TTL': '10'})
    @patch('minibus.services_tracking.fetch_fleet_locations')
    def test_second_call_within_ttl_is_cache_hit(self, mock_fetch):
        mock_fetch.return_value = self.fleet_payload

        payload1, meta1 = get_fleet_tracking(self.island)
        payload2, meta2 = get_fleet_tracking(self.island)

        self.assertEqual(payload1, self.fleet_payload)
        self.assertEqual(payload2, self.fleet_payload)
        self.assertEqual(meta1.cache_status, 'miss')
        self.assertEqual(meta2.cache_status, 'hit')
        mock_fetch.assert_called_once()

    @patch.dict('os.environ', {'MINIBUS_TRACKING_CACHE_TTL': '10'})
    @patch('minibus.services_tracking.fetch_fleet_locations')
    def test_call_after_ttl_refreshes(self, mock_fetch):
        mock_fetch.return_value = self.fleet_payload

        get_fleet_tracking(self.island)
        cache_key = f'minibus:tracking:fleet:{self.island.key}'
        envelope = cache.get(cache_key)
        stale_time = (timezone.now() - timedelta(seconds=11)).isoformat()
        cache.set(
            cache_key,
            {'payload': envelope['payload'], 'fetched_at': stale_time},
            70,
        )
        get_fleet_tracking(self.island)

        self.assertEqual(mock_fetch.call_count, 2)

    @patch.dict('os.environ', {'MINIBUS_TRACKING_CACHE_TTL': '5'})
    @patch('minibus.services_tracking.fetch_fleet_locations')
    def test_configurable_ttl_boundary(self, mock_fetch):
        mock_fetch.return_value = self.fleet_payload

        get_fleet_tracking(self.island)
        cache_key = f'minibus:tracking:fleet:{self.island.key}'
        envelope = cache.get(cache_key)

        cache.set(
            cache_key,
            {
                'payload': envelope['payload'],
                'fetched_at': (timezone.now() - timedelta(seconds=4)).isoformat(),
            },
            70,
        )
        _, meta_hit = get_fleet_tracking(self.island)

        cache.set(
            cache_key,
            {
                'payload': envelope['payload'],
                'fetched_at': (timezone.now() - timedelta(seconds=6)).isoformat(),
            },
            70,
        )
        get_fleet_tracking(self.island)

        self.assertEqual(meta_hit.cache_status, 'hit')
        self.assertEqual(mock_fetch.call_count, 2)

    @patch.dict('os.environ', {'MINIBUS_TRACKING_CACHE_TTL': '10', 'MINIBUS_TRACKING_STALE_GRACE': '60'})
    @patch('minibus.services_tracking.fetch_fleet_locations')
    def test_upstream_failure_serves_stale_within_grace(self, mock_fetch):
        mock_fetch.return_value = self.fleet_payload
        get_fleet_tracking(self.island)

        cache_key = f'minibus:tracking:fleet:{self.island.key}'
        envelope = cache.get(cache_key)
        cache.set(
            cache_key,
            {
                'payload': envelope['payload'],
                'fetched_at': (timezone.now() - timedelta(seconds=15)).isoformat(),
            },
            70,
        )
        mock_fetch.side_effect = MinibusTrackingError('upstream down')
        payload, meta = get_fleet_tracking(self.island)

        self.assertEqual(payload, self.fleet_payload)
        self.assertEqual(meta.cache_status, 'stale')
        self.assertTrue(meta.stale)

    @patch.dict('os.environ', {'MINIBUS_TRACKING_CACHE_TTL': '10', 'MINIBUS_TRACKING_STALE_GRACE': '60'})
    @patch('minibus.services_tracking.fetch_fleet_locations')
    @patch('minibus.services_tracking.timezone.now')
    def test_upstream_failure_without_cache_raises(self, mock_now, mock_fetch):
        mock_fetch.side_effect = MinibusTrackingError('upstream down')
        with self.assertRaises(MinibusTrackingError):
            get_fleet_tracking(self.island)

    @patch.dict('os.environ', {'MINIBUS_TRACKING_CACHE_TTL': '10', 'MINIBUS_TRACKING_STALE_GRACE': '60'})
    @patch('minibus.services_tracking.fetch_fleet_locations')
    def test_upstream_failure_after_stale_grace_raises(self, mock_fetch):
        mock_fetch.return_value = self.fleet_payload
        get_fleet_tracking(self.island)

        cache_key = f'minibus:tracking:fleet:{self.island.key}'
        envelope = cache.get(cache_key)
        cache.set(
            cache_key,
            {
                'payload': envelope['payload'],
                'fetched_at': (timezone.now() - timedelta(seconds=61)).isoformat(),
            },
            70,
        )
        mock_fetch.side_effect = MinibusTrackingError('upstream down')
        with self.assertRaises(MinibusTrackingError):
            get_fleet_tracking(self.island)


class VehicleTrackingCacheTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.island = get_or_create_default_island()
        self.detail_payload = {
            'id': '11010939',
            'journey': {'shape': 'abc', 'circulations': []},
            'currentStopSequence': 10,
        }

    @patch.dict('os.environ', {'MINIBUS_TRACKING_CACHE_TTL': '10'})
    @patch('minibus.services_tracking.fetch_vehicle_location')
    def test_vehicle_detail_cache_hit(self, mock_fetch):
        mock_fetch.return_value = self.detail_payload

        get_vehicle_tracking(self.island, '11010939')
        _, meta = get_vehicle_tracking(self.island, '11010939')

        self.assertEqual(meta.cache_status, 'hit')
        mock_fetch.assert_called_once_with('11010939')
