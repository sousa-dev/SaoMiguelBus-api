"""The sync command's guards, which are the parts that prevent damage.

--dry-run must fetch nothing. The holiday guard must hard-fail rather than
derive poisoned patterns. The data floor must be unreachable. An explicit
--dates window must never be treated as evidence that anything outside it is
gone.
"""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from tenancy.services import get_or_create_default_island
from transit.models import Holiday


class SyncCommandTests(TestCase):
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

    def test_a_real_run_is_not_silently_a_no_op(self):
        """Until the fetch phase lands, a non-dry run must say so, not pass."""
        with self.assertRaises(CommandError) as ctx:
            self._run()
        self.assertIn('not wired up', str(ctx.exception))
