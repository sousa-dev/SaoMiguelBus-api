"""Parish proximity mapping tests."""

from datetime import datetime
from unittest.mock import patch

from django.test import TestCase, override_settings

from tenancy.services import get_or_create_default_island
from weather.models import Parish, ParishProximity
from weather.services import nearest_parish, parish_snapshot, resolve_parish
from weather.tests.test_weather import SAMPLE_HOURLY_RAW, SAMPLE_RAW


class ParishProximityTestCase(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        self.near_parish = Parish.objects.create(
            island=self.island,
            name='São Pedro',
            slug='test-proximity-sao-pedro',
            concelho='Ponta Delgada',
            latitude=37.7411,
            longitude=-25.6756,
            is_active=True,
        )
        self.far_parish = Parish.objects.create(
            island=self.island,
            name='Ribeira Seca',
            slug='test-proximity-ribeira-seca',
            concelho='Ribeira Grande',
            latitude=37.8219,
            longitude=-25.5186,
            is_active=True,
        )
        self.inactive_parish = Parish.objects.create(
            island=self.island,
            name='Inactive Parish',
            slug='test-proximity-inactive',
            concelho='Ponta Delgada',
            latitude=37.7410,
            longitude=-25.6755,
            is_active=False,
        )

    def test_nearest_parish_returns_closest_active_parish(self):
        parish, distance_km = nearest_parish(
            self.island,
            self.near_parish.latitude,
            self.near_parish.longitude,
        )
        self.assertEqual(parish, self.near_parish)
        self.assertLess(distance_km, 1.0)

        farther_point_lat = 37.80
        farther_point_lon = -25.55
        parish, _distance = nearest_parish(self.island, farther_point_lat, farther_point_lon)
        self.assertEqual(parish, self.far_parish)

    def test_nearest_parish_ignores_inactive(self):
        parish, distance_km = nearest_parish(
            self.island,
            self.inactive_parish.latitude,
            self.inactive_parish.longitude,
        )
        self.assertEqual(parish, self.near_parish)
        self.assertGreater(distance_km, 0.0)

    def test_resolve_parish_creates_row_on_miss(self):
        lat = 37.7420
        lon = -25.6760
        self.assertEqual(ParishProximity.objects.count(), 0)

        parish = resolve_parish(
            self.island,
            'transit_stop',
            'stop-42',
            lat,
            lon,
        )

        self.assertEqual(parish, self.near_parish)
        self.assertEqual(ParishProximity.objects.count(), 1)
        row = ParishProximity.objects.get()
        self.assertEqual(row.source_module, 'transit_stop')
        self.assertEqual(row.source_ref, 'stop-42')
        self.assertEqual(row.parish, self.near_parish)
        self.assertAlmostEqual(row.latitude, lat)
        self.assertAlmostEqual(row.longitude, lon)
        self.assertGreater(row.distance_km, 0.0)
        self.assertLess(row.distance_km, 1.0)

    def test_resolve_parish_reuses_row_without_recompute(self):
        lat = 37.7420
        lon = -25.6760
        first = resolve_parish(self.island, 'transit_stop', 'stop-99', lat, lon)
        second = resolve_parish(self.island, 'transit_stop', 'stop-99', lat, lon)

        self.assertEqual(first, second)
        self.assertEqual(ParishProximity.objects.count(), 1)


class ParishSnapshotTestCase(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.island = get_or_create_default_island()
        self.parish = Parish.objects.create(
            island=self.island,
            name='São Pedro',
            slug='test-snapshot-sao-pedro',
            concelho='Ponta Delgada',
            latitude=37.7411,
            longitude=-25.6756,
            is_active=True,
        )

    @override_settings(
        CACHES={
            'default': {
                'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            }
        },
    )
    @patch('weather.services.fetch_forecast', return_value=[SAMPLE_RAW])
    def test_parish_snapshot_current_mode(self, _mock_forecast):
        from weather.services import refresh_parishes

        refresh_parishes([self.parish])
        cell = parish_snapshot(self.parish, at=None, distance_km=0.42)

        self.assertIsNotNone(cell)
        assert cell is not None
        self.assertEqual(cell['slug'], self.parish.slug)
        self.assertEqual(cell['name'], self.parish.name)
        self.assertEqual(cell['concelho'], self.parish.concelho)
        self.assertEqual(cell['source'], 'current')
        self.assertAlmostEqual(cell['distanceKm'], 0.42)
        self.assertIsNone(cell['at'])
        self.assertEqual(cell['temperature'], 18.5)
        self.assertEqual(cell['weatherCode'], 1)
        self.assertEqual(cell['windSpeed'], 12.0)
        self.assertEqual(cell['humidity'], 70)
        self.assertEqual(cell['precipitation'], 0.0)

    @override_settings(
        CACHES={
            'default': {
                'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            }
        },
    )
    @patch('weather.services.fetch_hourly', return_value=SAMPLE_HOURLY_RAW)
    @patch('weather.services.fetch_forecast', return_value=[SAMPLE_RAW])
    def test_parish_snapshot_forecast_at_hour(self, _mock_forecast, _mock_hourly):
        from weather.services import refresh_parishes

        refresh_parishes([self.parish])
        at = datetime.fromisoformat('2026-06-03T14:00:00')
        cell = parish_snapshot(self.parish, at=at)

        self.assertIsNotNone(cell)
        assert cell is not None
        self.assertEqual(cell['source'], 'forecast')
        self.assertEqual(cell['at'], '2026-06-03T14:00')
        self.assertEqual(cell['temperature'], 18.0 + (14 % 5))
        self.assertEqual(cell['weatherCode'], 1)

    @override_settings(
        CACHES={
            'default': {
                'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            }
        },
    )
    @patch('weather.services.fetch_forecast', return_value=[SAMPLE_RAW])
    def test_parish_snapshot_returns_none_beyond_window(self, _mock_forecast):
        from weather.services import refresh_parishes

        refresh_parishes([self.parish])
        at = datetime.fromisoformat('2026-06-10T12:00:00')
        cell = parish_snapshot(self.parish, at=at)
        self.assertIsNone(cell)
