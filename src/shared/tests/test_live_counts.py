"""Cache primitives behind `GET /api/v3/transit/live-counts`."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from shared.live_counts import (
    is_refresh_daytime,
    mark_refresh_attempt,
    needs_refresh,
    read_live_count,
    record_live_count,
    record_live_outage,
    should_attempt_refresh,
)

AZORES = ZoneInfo('Atlantic/Azores')
LOC_MEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}


@override_settings(CACHES=LOC_MEM_CACHE)
class RecordAndReadTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_record_then_read_roundtrip(self):
        record_live_count('azoresbus', 'sao-miguel', 12, fetched_at=timezone.now())
        record = read_live_count('azoresbus', 'sao-miguel')

        self.assertEqual(record['status'], 'ok')
        self.assertEqual(record['vehicles'], 12)
        self.assertIn('recordedAt', record)

    def test_record_outage_reads_unavailable_with_null_vehicles(self):
        record_live_outage('minibus', 'sao-miguel')
        record = read_live_count('minibus', 'sao-miguel')

        self.assertEqual(record['status'], 'unavailable')
        self.assertIsNone(record['vehicles'])

    def test_missing_record_reads_none(self):
        self.assertIsNone(read_live_count('azoresbus', 'sao-miguel'))

    def test_operators_and_islands_do_not_leak_into_each_other(self):
        record_live_count('azoresbus', 'sao-miguel', 5, fetched_at=timezone.now())

        self.assertIsNone(read_live_count('minibus', 'sao-miguel'))
        self.assertIsNone(read_live_count('azoresbus', 'terceira'))

    @patch.dict('os.environ', {'LIVE_COUNT_TTL': '60'})
    def test_read_returns_none_once_recordedAt_is_older_than_ttl(self):
        """Age is judged by `recordedAt`, not by when Redis happens to evict.

        Rewriting the envelope rather than sleeping is the same trick the
        minibus fleet-cache tests use to simulate TTL expiry.
        """
        record_live_count('azoresbus', 'sao-miguel', 3, fetched_at=timezone.now())
        stale_envelope = cache.get('live:count:azoresbus:sao-miguel')
        stale_envelope['recordedAt'] = (timezone.now() - timedelta(seconds=61)).isoformat()
        cache.set('live:count:azoresbus:sao-miguel', stale_envelope, 3600)

        self.assertIsNone(read_live_count('azoresbus', 'sao-miguel'))

    @patch.dict('os.environ', {'LIVE_COUNT_TTL': '60'})
    def test_a_record_just_inside_the_ttl_still_reads(self):
        record_live_count('azoresbus', 'sao-miguel', 3, fetched_at=timezone.now())
        envelope = cache.get('live:count:azoresbus:sao-miguel')
        envelope['recordedAt'] = (timezone.now() - timedelta(seconds=59)).isoformat()
        cache.set('live:count:azoresbus:sao-miguel', envelope, 3600)

        self.assertIsNotNone(read_live_count('azoresbus', 'sao-miguel'))


class LiveCountTtlEnvTests(TestCase):
    @patch.dict('os.environ', {'LIVE_COUNT_TTL': '300'})
    def test_ttl_from_env(self):
        from shared.live_counts import get_live_count_ttl

        self.assertEqual(get_live_count_ttl(), 300)

    @patch.dict('os.environ', {'LIVE_COUNT_TTL': '5'})
    def test_ttl_clamped_to_minimum(self):
        from shared.live_counts import get_live_count_ttl

        self.assertEqual(get_live_count_ttl(), 60)

    @patch.dict('os.environ', {'LIVE_COUNT_TTL': '999999'})
    def test_ttl_clamped_to_maximum(self):
        from shared.live_counts import get_live_count_ttl

        self.assertEqual(get_live_count_ttl(), 6 * 3600)


@override_settings(CACHES=LOC_MEM_CACHE)
class RefreshAttemptTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_first_attempt_wins_then_the_window_blocks_further_attempts(self):
        self.assertTrue(mark_refresh_attempt('azoresbus', 'sao-miguel'))
        self.assertFalse(mark_refresh_attempt('azoresbus', 'sao-miguel'))

    def test_operators_have_independent_windows(self):
        self.assertTrue(mark_refresh_attempt('azoresbus', 'sao-miguel'))
        self.assertTrue(mark_refresh_attempt('minibus', 'sao-miguel'))


class DaytimeBoundaryTests(TestCase):
    def _at(self, hour: int, minute: int = 0) -> datetime:
        return datetime(2026, 9, 4, hour, minute, tzinfo=AZORES)

    def test_just_before_six_is_night(self):
        self.assertFalse(is_refresh_daytime(self._at(5, 59)))

    def test_six_sharp_is_daytime(self):
        self.assertTrue(is_refresh_daytime(self._at(6, 0)))

    def test_just_before_seven_pm_is_still_daytime(self):
        self.assertTrue(is_refresh_daytime(self._at(18, 59)))

    def test_seven_pm_sharp_is_night(self):
        self.assertFalse(is_refresh_daytime(self._at(19, 0)))

    def test_midnight_is_night(self):
        self.assertFalse(is_refresh_daytime(self._at(0, 0)))


class NeedsRefreshTests(TestCase):
    def test_no_record_needs_a_refresh(self):
        self.assertTrue(needs_refresh(None))

    def test_a_recorded_zero_needs_a_refresh(self):
        self.assertTrue(needs_refresh({'status': 'ok', 'vehicles': 0}))

    def test_a_recorded_outage_needs_a_refresh(self):
        self.assertTrue(needs_refresh({'status': 'unavailable', 'vehicles': None}))

    def test_a_recorded_nonzero_count_does_not_need_a_refresh(self):
        self.assertFalse(needs_refresh({'status': 'ok', 'vehicles': 5}))


class ShouldAttemptRefreshTests(TestCase):
    """A completely missing record is the one case that ignores the clock --
    a fresh deploy or a Redis flush must self-heal without waiting for
    morning, since MiniBus (unlike AzoresBus) has no background sweep of its
    own keeping it warm."""

    NIGHT = datetime(2026, 9, 4, 23, 0, tzinfo=AZORES)
    DAY = datetime(2026, 9, 4, 12, 0, tzinfo=AZORES)

    def test_no_record_refreshes_even_at_night(self):
        self.assertTrue(should_attempt_refresh(None, now=self.NIGHT))

    def test_no_record_refreshes_in_daytime_too(self):
        self.assertTrue(should_attempt_refresh(None, now=self.DAY))

    def test_a_recorded_zero_only_refreshes_in_daytime(self):
        record = {'status': 'ok', 'vehicles': 0}
        self.assertFalse(should_attempt_refresh(record, now=self.NIGHT))
        self.assertTrue(should_attempt_refresh(record, now=self.DAY))

    def test_a_recorded_outage_only_refreshes_in_daytime(self):
        record = {'status': 'unavailable', 'vehicles': None}
        self.assertFalse(should_attempt_refresh(record, now=self.NIGHT))
        self.assertTrue(should_attempt_refresh(record, now=self.DAY))

    def test_a_healthy_record_never_needs_a_refresh(self):
        record = {'status': 'ok', 'vehicles': 5}
        self.assertFalse(should_attempt_refresh(record, now=self.NIGHT))
        self.assertFalse(should_attempt_refresh(record, now=self.DAY))
