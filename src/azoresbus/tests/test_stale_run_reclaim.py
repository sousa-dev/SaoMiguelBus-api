"""A killed worker must not lock out every future sync.

Real incident: a redeploy killed a worker mid-sync. `finally:
release_sync_lock()` does not run on SIGKILL, so the Redis lock survived with
its full 45-minute TTL, and the deploy's own bootstrap_azoresbus then got
`{'queued': False, 'reason': 'another sync holds the lock'}` and silently did
nothing. Meanwhile the SyncRun row sat at Running forever, since the process
that owned it no longer existed.

Net effect: redeploying during a sync disabled syncing for 45 minutes, and
looked healthy the whole time.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from azoresbus.models import SyncRun
from azoresbus.services_sync import reclaim_stale_runs
from tenancy.services import get_or_create_default_island

LOC_MEM_CACHE = {
    'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
}


@override_settings(CACHES=LOC_MEM_CACHE)
class ReclaimStaleRunsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.island = get_or_create_default_island()

    def _run(self, *, status=SyncRun.STATUS_RUNNING, minutes_ago=0):
        return SyncRun.objects.create(
            island=self.island,
            kind=SyncRun.KIND_SCHEDULES,
            status=status,
            started_at=timezone.now() - timedelta(minutes=minutes_ago),
        )

    def test_an_orphaned_running_row_is_marked_partial(self):
        run = self._run(minutes_ago=90)

        reclaimed = reclaim_stale_runs(self.island)

        run.refresh_from_db()
        self.assertEqual(reclaimed, 1)
        self.assertEqual(run.status, SyncRun.STATUS_PARTIAL)
        self.assertIn('orphan', run.error.lower())
        self.assertIsNotNone(run.finished_at)

    def test_a_recent_running_row_is_left_alone_by_default(self):
        """A sync legitimately in flight must not be killed."""
        run = self._run(minutes_ago=2)

        reclaimed = reclaim_stale_runs(self.island)

        run.refresh_from_db()
        self.assertEqual(reclaimed, 0)
        self.assertEqual(run.status, SyncRun.STATUS_RUNNING)

    def test_all_running_reclaims_regardless_of_age(self):
        """On deploy every worker just restarted, so nothing can still be alive."""
        run = self._run(minutes_ago=1)

        reclaimed = reclaim_stale_runs(self.island, all_running=True)

        run.refresh_from_db()
        self.assertEqual(reclaimed, 1)
        self.assertEqual(run.status, SyncRun.STATUS_PARTIAL)

    def test_completed_runs_are_never_touched(self):
        run = self._run(status=SyncRun.STATUS_COMPLETED, minutes_ago=999)

        reclaim_stale_runs(self.island, all_running=True)

        run.refresh_from_db()
        self.assertEqual(run.status, SyncRun.STATUS_COMPLETED)
        self.assertEqual(run.error, '')

    def test_reclaiming_releases_the_stale_lock(self):
        """The whole point: a new sync must be able to start afterwards."""
        from azoresbus.tasks import acquire_sync_lock

        self.assertTrue(acquire_sync_lock())      # simulate the dead worker's lock
        self._run(minutes_ago=90)

        reclaim_stale_runs(self.island)

        self.assertTrue(
            acquire_sync_lock(),
            'the lock was still held, so the next sync would be blocked',
        )

    def test_nothing_to_reclaim_leaves_a_held_lock_alone(self):
        """A genuinely running sync keeps its lock."""
        from azoresbus.tasks import acquire_sync_lock

        self.assertTrue(acquire_sync_lock())
        self._run(minutes_ago=2)

        reclaim_stale_runs(self.island)

        self.assertFalse(
            acquire_sync_lock(),
            'released a lock belonging to a live run',
        )


@override_settings(CACHES=LOC_MEM_CACHE)
class BootstrapReclaimsBeforeQueueingTests(TestCase):
    """The deploy path must recover from its own previous kill."""

    def setUp(self):
        cache.clear()
        self.island = get_or_create_default_island()

    def _bootstrap(self, *args):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command('bootstrap_azoresbus', *args, stdout=out, stderr=out)
        return out.getvalue()

    @patch('azoresbus.tasks.sync_schedules_task.apply_async')
    def test_a_stale_lock_does_not_block_the_deploy_sync(self, mock_apply):
        from azoresbus.tasks import acquire_sync_lock

        # Exactly the production state: dead worker's lock + orphaned row.
        acquire_sync_lock()
        SyncRun.objects.create(
            island=self.island,
            kind=SyncRun.KIND_SCHEDULES,
            status=SyncRun.STATUS_RUNNING,
            started_at=timezone.now() - timedelta(minutes=5),
        )

        output = self._bootstrap()

        mock_apply.assert_called_once()
        self.assertIn('queued', output.lower())

    @patch('azoresbus.tasks.sync_schedules_task.apply_async')
    def test_the_orphaned_row_is_resolved_not_left_running(self, mock_apply):
        orphan = SyncRun.objects.create(
            island=self.island,
            kind=SyncRun.KIND_SCHEDULES,
            status=SyncRun.STATUS_RUNNING,
            started_at=timezone.now() - timedelta(minutes=5),
        )

        self._bootstrap()

        orphan.refresh_from_db()
        self.assertEqual(orphan.status, SyncRun.STATUS_PARTIAL)

    @patch('azoresbus.tasks.sync_schedules_task.apply_async')
    def test_reclaimed_runs_are_reported(self, mock_apply):
        SyncRun.objects.create(
            island=self.island,
            kind=SyncRun.KIND_SCHEDULES,
            status=SyncRun.STATUS_RUNNING,
            started_at=timezone.now() - timedelta(minutes=5),
        )

        output = self._bootstrap()

        self.assertIn('reclaimed', output.lower())
