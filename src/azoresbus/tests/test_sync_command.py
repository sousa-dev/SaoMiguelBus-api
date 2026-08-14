"""The sync command's guards, which are the parts that prevent damage.

--dry-run must fetch nothing. The holiday guard must hard-fail rather than
derive poisoned patterns. The data floor must be unreachable. An explicit
--dates window must never be treated as evidence that anything outside it is
gone.
"""

from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from tenancy.services import get_or_create_default_island
from transit.models import Holiday


class SyncCommandTests(TestCase):
    """Nothing here may touch the network.

    An earlier version of this module let a non-dry run reach upstream and
    issued 55 routes x 18 dates of live requests before it was killed. The
    patched `requests.get` in every non-dry test is load-bearing, not decorative.
    """

    def setUp(self):
        self.island = get_or_create_default_island()

    def _run(self, *args) -> str:
        out = StringIO()
        call_command('sync_azoresbus', *args, stdout=out, stderr=out)
        return out.getvalue()

    # -- dry run ------------------------------------------------------------

    @patch('azoresbus.client.requests.get')
    def test_dry_run_touches_the_network_never(self, mock_get):
        output = self._run('--dry-run')

        mock_get.assert_not_called()
        self.assertIn('DRY RUN', output)
        self.assertIn('nothing fetched, nothing written', output)

    def test_dry_run_reports_the_sample_and_the_budget(self):
        output = self._run('--dry-run')

        self.assertIn('sampled dates', output)
        self.assertIn('requests', output)
        self.assertIn('cap', output)
        self.assertIn('2026-07-27', output)      # the data floor, stated

    def test_dry_run_reports_the_retirement_decision(self):
        """You should not have to guess whether a run would remove service."""
        output = self._run('--dry-run')
        self.assertIn('retirement', output)
        self.assertIn('baseline', output)        # no previous run yet

    # -- the holiday guard (98 B6) ------------------------------------------

    def test_a_year_with_no_holiday_rows_hard_fails(self):
        """An empty holiday year is a seeding bug, not a year without holidays.

        Regression test for the production state found 2026-08-14: 16 rows,
        newest 2025-06-19. Deriving through that records Sunday journey sets as
        weekday service.
        """
        Holiday.objects.filter(island=self.island).delete()

        with self.assertRaises(CommandError) as ctx:
            self._run('--dry-run')

        message = str(ctx.exception)
        self.assertIn('Holiday', message)
        self.assertIn('98 B6', message)

    def test_the_seeded_table_satisfies_the_guard(self):
        self._run('--dry-run')          # must not raise

    # -- the data floor (98 B1) ---------------------------------------------

    def test_dates_below_the_floor_are_refused(self):
        with self.assertRaises(CommandError) as ctx:
            self._run('--dry-run', '--dates', '2026-07-01..2026-07-03')

        self.assertIn('data floor', str(ctx.exception))

    def test_a_valid_explicit_window_is_accepted(self):
        output = self._run('--dry-run', '--dates', '2026-09-14..2026-09-20')

        for day in range(14, 21):
            self.assertIn(f'2026-09-{day}', output)

    def test_explicit_dates_imply_no_prune(self):
        """A hand-picked window is not evidence that anything else is gone."""
        output = self._run('--dry-run', '--dates', '2026-09-14..2026-09-20')

        self.assertIn('suppressed', output)

    def test_malformed_dates_are_rejected(self):
        for bad in ('monday', '2026-13-01', '2026-09-20..2026-09-14'):
            with self.assertRaises(CommandError, msg=f'{bad} was accepted'):
                self._run('--dry-run', '--dates', bad)

    # -- misc ---------------------------------------------------------------

    def test_unknown_island_fails_loudly(self):
        with self.assertRaises(CommandError):
            self._run('--dry-run', '--island', 'atlantis')

    @patch('azoresbus.client.time.sleep')          # no real backoff waits
    @patch('azoresbus.client.requests.get')
    def test_a_failed_fetch_marks_the_run_partial_and_retires_nothing(
        self, mock_get, _sleep,
    ):
        """A network failure must not look like a deletion."""
        import requests

        from azoresbus.models import SyncRun

        mock_get.side_effect = requests.RequestException('upstream down')

        with self.assertRaises(CommandError) as ctx:
            self._run()

        self.assertIn('partial', str(ctx.exception).lower())
        run = SyncRun.objects.latest('started_at')
        self.assertEqual(run.status, SyncRun.STATUS_PARTIAL)
        self.assertTrue(run.error)
        self.assertNotIn('retirement', (run.stats or {}))

    @patch('azoresbus.client.time.sleep')
    @patch('azoresbus.client.requests.get')
    def test_the_budget_cap_stops_a_run_before_it_half_writes(
        self, mock_get, _sleep,
    ):
        """Hitting the cap marks the run partial; it never retires (02 §4.3).

        The cap has to bite during the listing loop, so upstream must return a
        real route list -- an empty one never spends the budget.
        """
        from azoresbus.models import SyncRun

        routes = [{'id': str(n), 'nameShort': f'1{n:02d}', 'name': 'R',
                   'isActive': True} for n in range(1, 56)]

        def responses(url, **kwargs):
            body = routes if '/routes?' in url else []
            return MagicMock(ok=True, status_code=200, json=lambda: body,
                             headers={}, text='')

        mock_get.side_effect = responses

        with self.assertRaises(CommandError) as ctx:
            self._run('--max-requests', '10')

        self.assertIn('partial', str(ctx.exception).lower())
        run = SyncRun.objects.latest('started_at')
        self.assertEqual(run.status, SyncRun.STATUS_PARTIAL)
        self.assertLessEqual(run.request_count, 10)
