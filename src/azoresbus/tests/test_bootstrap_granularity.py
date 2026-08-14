"""The deploy bootstrap syncs what is MISSING, not everything or nothing.

Schedules and tariffs are independent: a deploy that already has 989 journeys
but no fare tables should fetch one conditional request, not re-run a
2000-request schedule sync. And a re-deploy with both present should cost
nothing at all.
"""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from azoresbus.models import SyncRun, TariffSnapshot
from tenancy.services import for_island, get_or_create_default_island
from transit.models import DATASET_AZORESBUS, Line, Operator, Trip


class BootstrapGranularityTests(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()

    def _run(self, *args) -> str:
        out = StringIO()
        call_command('bootstrap_azoresbus', *args, stdout=out, stderr=out)
        return out.getvalue()

    def _have_schedules(self):
        operator, _ = Operator.objects.get_or_create(
            island=self.island, name='AzoresBus', defaults={'contact': {}},
        )
        line = Line.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, code='101',
            operator=operator,
        )
        Trip.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, line=line,
            source=Trip.SOURCE_OPERATOR,
        )
        SyncRun.objects.create(
            island=self.island, kind=SyncRun.KIND_SCHEDULES,
            status=SyncRun.STATUS_COMPLETED,
        )

    def _have_tariffs(self):
        with for_island(self.island):
            TariffSnapshot.objects.create(
                island=self.island, source_url='https://x',
                payload={'date': '2026-09-01'}, content_hash='abc',
                is_current=True,
            )

    # -- nothing missing -----------------------------------------------------

    @patch('azoresbus.management.commands.bootstrap_azoresbus.queue_tariffs')
    @patch('azoresbus.management.commands.bootstrap_azoresbus.queue_sync')
    def test_a_redeploy_with_everything_present_costs_nothing(
        self, mock_sync, mock_tariffs,
    ):
        self._have_schedules()
        self._have_tariffs()

        output = self._run()

        mock_sync.assert_not_called()
        mock_tariffs.assert_not_called()
        self.assertIn('up to date', output.lower())

    # -- only tariffs missing ------------------------------------------------

    @patch('azoresbus.management.commands.bootstrap_azoresbus.queue_tariffs')
    @patch('azoresbus.management.commands.bootstrap_azoresbus.queue_sync')
    def test_missing_tariffs_alone_does_not_trigger_a_schedule_sync(
        self, mock_sync, mock_tariffs,
    ):
        """One conditional request, not a 2000-request run."""
        self._have_schedules()

        output = self._run()

        mock_tariffs.assert_called_once()
        mock_sync.assert_not_called()
        self.assertIn('tariffs', output.lower())

    # -- schedules missing ---------------------------------------------------

    @patch('azoresbus.management.commands.bootstrap_azoresbus.queue_tariffs')
    @patch('azoresbus.management.commands.bootstrap_azoresbus.queue_sync')
    def test_missing_schedules_queues_a_full_sync(self, mock_sync, mock_tariffs):
        self._have_tariffs()

        self._run()

        mock_sync.assert_called_once()
        self.assertTrue(mock_sync.call_args.kwargs['full'])

    @patch('azoresbus.management.commands.bootstrap_azoresbus.queue_tariffs')
    @patch('azoresbus.management.commands.bootstrap_azoresbus.queue_sync')
    def test_a_schedule_sync_covers_tariffs_so_they_are_not_queued_twice(
        self, mock_sync, mock_tariffs,
    ):
        """run_sync fetches tariffs as a step; queueing both would duplicate."""
        self._run()          # nothing present at all

        mock_sync.assert_called_once()
        mock_tariffs.assert_not_called()

    # -- force ---------------------------------------------------------------

    @patch('azoresbus.management.commands.bootstrap_azoresbus.queue_tariffs')
    @patch('azoresbus.management.commands.bootstrap_azoresbus.queue_sync')
    def test_force_syncs_everything_regardless(self, mock_sync, mock_tariffs):
        self._have_schedules()
        self._have_tariffs()

        self._run('--force')

        mock_sync.assert_called_once()


class SyncIncludesTariffsTests(TestCase):
    """A schedule run refreshes fares too: it is one conditional request."""

    def setUp(self):
        self.island = get_or_create_default_island()

    @patch('azoresbus.services_tariffs.sync_tariffs')
    @patch('azoresbus.services_sync._fetch_all')
    def test_run_sync_also_syncs_tariffs(self, mock_fetch, mock_tariffs):
        from azoresbus.services_sync import run_sync

        mock_fetch.return_value = {
            'stops': [], 'routes': [], 'journeys': {}, 'details': {},
        }
        mock_tariffs.return_value = {'changed': True, 'snapshot_id': 1}

        with for_island(self.island):
            report = run_sync(self.island, full=True)

        mock_tariffs.assert_called_once()
        self.assertTrue(report['tariffs']['changed'])

    @patch('azoresbus.services_tariffs.sync_tariffs')
    @patch('azoresbus.services_sync._fetch_all')
    def test_a_tariff_failure_does_not_fail_the_schedule_run(
        self, mock_fetch, mock_tariffs,
    ):
        """Fares going stale is not a reason to lose a timetable import."""
        from azoresbus.services_tariffs import TariffsError
        from azoresbus.services_sync import run_sync

        mock_fetch.return_value = {
            'stops': [], 'routes': [], 'journeys': {}, 'details': {},
        }
        mock_tariffs.side_effect = TariffsError('azoresbus.pt down')

        with for_island(self.island):
            report = run_sync(self.island, full=True)

        self.assertIn('error', report['tariffs'])
        run = SyncRun.objects.latest('started_at')
        self.assertEqual(run.status, SyncRun.STATUS_COMPLETED)
