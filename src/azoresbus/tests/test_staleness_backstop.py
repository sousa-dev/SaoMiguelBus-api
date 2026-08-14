"""02 §4.6: a backstop for when beat is not running at all.

No successful sync in 10 days is the highest-likelihood way this goes wrong
silently, so the read path checks and enqueues. It must never delay or fail a
search.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from azoresbus.models import SyncRun
from azoresbus.tasks import maybe_queue_stale_sync
from tenancy.services import get_or_create_default_island


LOC_MEM_CACHE = {
    'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
}


@override_settings(CACHES=LOC_MEM_CACHE)
class StalenessBackstopTests(TestCase):
    def setUp(self):
        cache.clear()
        self.island = get_or_create_default_island()

    def _run(self, *, days_ago=None, status=SyncRun.STATUS_COMPLETED):
        if days_ago is not None:
            SyncRun.objects.create(
                island=self.island,
                kind=SyncRun.KIND_SCHEDULES,
                status=status,
                started_at=timezone.now() - timedelta(days=days_ago),
            )

    @patch('azoresbus.tasks.sync_schedules_task.apply_async')
    def test_a_fresh_sync_enqueues_nothing(self, mock_apply):
        self._run(days_ago=1)
        self.assertFalse(maybe_queue_stale_sync(self.island))
        mock_apply.assert_not_called()

    @patch('azoresbus.tasks.sync_schedules_task.apply_async')
    def test_a_stale_sync_enqueues(self, mock_apply):
        self._run(days_ago=11)
        self.assertTrue(maybe_queue_stale_sync(self.island))
        mock_apply.assert_called_once()

    @patch('azoresbus.tasks.sync_schedules_task.apply_async')
    def test_never_having_synced_enqueues_a_full_run(self, mock_apply):
        self.assertTrue(maybe_queue_stale_sync(self.island))
        self.assertTrue(mock_apply.call_args.kwargs['kwargs']['full'])

    @patch('azoresbus.tasks.sync_schedules_task.apply_async')
    def test_a_partial_run_does_not_count_as_success(self, mock_apply):
        self._run(days_ago=1, status=SyncRun.STATUS_PARTIAL)
        self.assertTrue(maybe_queue_stale_sync(self.island))

    @patch('azoresbus.tasks.sync_schedules_task.apply_async')
    def test_concurrent_searches_enqueue_exactly_one_run(self, mock_apply):
        for _ in range(5):
            maybe_queue_stale_sync(self.island)
        self.assertEqual(mock_apply.call_count, 1)

    @patch('azoresbus.tasks.sync_schedules_task.apply_async')
    def test_a_broker_outage_never_breaks_a_search(self, mock_apply):
        mock_apply.side_effect = RuntimeError('no broker')
        self.assertFalse(maybe_queue_stale_sync(self.island))   # must not raise
