"""The first deployment after these changes must populate itself.

The hook is `runserver.sh`, the Dockerfile CMD, which already runs
bootstrap_atlas / import_minibus / bootstrap_feed_syncs after migrate. This
joins that chain.

NOT AppConfig.ready(), deliberately: runserver.sh ends with `gunicorn
--workers 3`, and celery worker and beat each load the app too. A ready() hook
would fire ~5 times concurrently -- roughly 10,750 requests at once against a
Cloudflare-fronted host with no published rate limit -- and would block startup
and health checks for ~13 minutes. It also runs before migrate on some paths and
during every test. The last test in this module pins that.
"""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings

from azoresbus.models import SyncRun
from tenancy.services import get_or_create_default_island
from transit.models import DATASET_AZORESBUS, Calendar, Line, Operator, Trip


# The lock is a cache key, and the default CACHES is Redis whenever REDIS_URL is
# set (it is, in src/.env). House pattern: transit/tests/test_route_weather.py.
LOC_MEM_CACHE = {
    'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
}


class BootstrapCommandTests(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()

    def _run(self, *args) -> str:
        out = StringIO()
        call_command('bootstrap_azoresbus', *args, stdout=out, stderr=out)
        return out.getvalue()

    def _make_azoresbus_trip(self) -> Trip:
        operator, _ = Operator.objects.get_or_create(
            island=self.island, name='AzoresBus', defaults={'contact': {}},
        )
        calendar, _ = Calendar.objects.get_or_create(
            island=self.island, service_type=Calendar.WEEKDAY,
        )
        line = Line.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, code='101',
            operator=operator,
        )
        return Trip.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, line=line,
            calendar=calendar, source=Trip.SOURCE_OPERATOR,
        )

    @patch('azoresbus.management.commands.bootstrap_azoresbus.queue_sync')
    def test_queues_a_full_run_when_there_is_no_data(self, mock_queue):
        output = self._run()

        mock_queue.assert_called_once()
        self.assertTrue(mock_queue.call_args.kwargs['full'])
        self.assertIn('queued', output.lower())

    @patch('azoresbus.management.commands.bootstrap_azoresbus.queue_sync')
    def test_no_op_when_data_and_a_successful_run_exist(self, mock_queue):
        self._make_azoresbus_trip()
        SyncRun.objects.create(
            island=self.island, kind=SyncRun.KIND_SCHEDULES,
            status=SyncRun.STATUS_COMPLETED,
        )

        output = self._run()

        mock_queue.assert_not_called()
        self.assertIn('up to date', output.lower())

    @patch('azoresbus.management.commands.bootstrap_azoresbus.queue_sync')
    def test_queues_when_trips_exist_but_no_run_ever_succeeded(self, mock_queue):
        """Half-imported data is worse than none; re-sync it."""
        self._make_azoresbus_trip()
        SyncRun.objects.create(
            island=self.island, kind=SyncRun.KIND_SCHEDULES,
            status=SyncRun.STATUS_PARTIAL,
        )

        self._run()
        mock_queue.assert_called_once()

    @patch('azoresbus.management.commands.bootstrap_azoresbus.queue_sync')
    def test_force_syncs_regardless_of_state(self, mock_queue):
        self._make_azoresbus_trip()
        SyncRun.objects.create(
            island=self.island, kind=SyncRun.KIND_SCHEDULES,
            status=SyncRun.STATUS_COMPLETED,
        )

        self._run('--force')
        mock_queue.assert_called_once()

    @patch('azoresbus.management.commands.bootstrap_azoresbus.queue_sync')
    def test_a_broker_outage_never_fails_the_deploy(self, mock_queue):
        """bootstrap_feed_syncs swallows its own exceptions; so does this."""
        mock_queue.side_effect = RuntimeError('no broker')

        output = self._run()          # must not raise

        self.assertIn('could not queue', output.lower())

    @override_settings(CACHES=LOC_MEM_CACHE)
    @patch('azoresbus.tasks.sync_schedules_task.apply_async')
    def test_only_one_run_is_queued_for_a_rolling_deploy(self, mock_apply):
        """Two web containers starting together must not start two syncs.

        Drives the real queue_sync so the lock is actually exercised -- mocking
        queue_sync would bypass the very thing under test.
        """
        cache.clear()
        self._run()
        self._run()

        self.assertEqual(
            mock_apply.call_count, 1,
            'the lock did not hold across concurrent deploy steps',
        )

    @override_settings(CACHES=LOC_MEM_CACHE)
    @patch('azoresbus.tasks.sync_schedules_task.apply_async')
    def test_the_lock_is_released_when_dispatch_fails(self, mock_apply):
        """A broker error must not wedge the lock for 45 minutes."""
        from azoresbus.tasks import acquire_sync_lock

        cache.clear()
        mock_apply.side_effect = RuntimeError('no broker')
        self._run()

        self.assertTrue(
            acquire_sync_lock(),
            'the lock was still held after a failed dispatch',
        )


class NotInAppReadyTests(TestCase):
    def test_no_app_config_triggers_a_sync_on_startup(self):
        """Pins the design decision so nobody re-adds it later.

        A ready() hook fires once per gunicorn worker, once per celery process
        and once per test run. With 3 workers plus worker and beat that is ~5
        concurrent full syncs.
        """
        from pathlib import Path

        src = Path(__file__).resolve().parents[2]
        offenders = []
        for apps_py in src.glob('*/apps.py'):
            body = apps_py.read_text(encoding='utf-8')
            if 'def ready' not in body:
                continue
            for needle in ('queue_sync', 'sync_schedules', 'bootstrap_azoresbus'):
                if needle in body:
                    offenders.append(f'{apps_py.name}: {needle}')

        self.assertEqual(
            offenders, [],
            'a sync is being triggered from AppConfig.ready(): '
            f'{offenders}. Use the runserver.sh deploy step instead.',
        )


class TaskDoesRealWorkTests(TestCase):
    """The task is what the deploy, beat and the backstop all trigger.

    It was a stub that logged 'pending' and returned. Everything would have
    looked healthy — queued tasks, no errors — while no data was ever fetched.
    """

    def test_the_task_calls_the_real_sync(self):
        from unittest.mock import patch as _patch

        get_or_create_default_island()
        with _patch('azoresbus.services_sync.run_sync') as mock_run:
            mock_run.return_value = {'lines': 55, 'stops': 816}
            from azoresbus.tasks import sync_schedules_task

            result = sync_schedules_task(island_key='sao-miguel', full=True)

        mock_run.assert_called_once()
        self.assertTrue(mock_run.call_args.kwargs['full'])
        self.assertEqual(result['islands']['sao-miguel']['lines'], 55)

    def test_a_failing_sync_releases_the_lock(self):
        from unittest.mock import patch as _patch

        from azoresbus.tasks import acquire_sync_lock, sync_schedules_task

        get_or_create_default_island()
        with override_settings(CACHES=LOC_MEM_CACHE):
            cache.clear()
            with _patch('azoresbus.services_sync.run_sync',
                        side_effect=RuntimeError('boom')):
                sync_schedules_task(island_key='sao-miguel')
            self.assertTrue(
                acquire_sync_lock(),
                'a crashed run wedged the lock for 45 minutes',
            )

    def test_the_task_does_not_sync_islands_without_azoresbus(self):
        from unittest.mock import patch as _patch

        from azoresbus.tasks import sync_schedules_task

        with _patch('azoresbus.services_sync.run_sync') as mock_run:
            mock_run.return_value = {}
            sync_schedules_task()

        for call in mock_run.call_args_list:
            self.assertEqual(call.args[0].key, 'sao-miguel')
