"""build_seed_db refuses to seed from a non-production database.

The seed carries each island's revision counter forward as the client's *starting sync
cursor*, so building it from the wrong database ships cursors that do not match the server the
app talks to. That shipped once and made delta sync a permanent no-op on every install — see
atlas/tests/test_future_cursor_resync.py for the other half of the fix.

The test database is sqlite, so the guard is exercised by default here.
"""

from __future__ import annotations

import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import CommandError, call_command
from django.db import connection
from django.test import TestCase

from atlas.models import AtlasRevision
from tenancy.services import get_or_create_default_island


class BuildSeedDbGuardTestCase(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        # sync_state in the seed is derived from AtlasRevision rows (one per island), which
        # bootstrap_atlas normally creates.
        AtlasRevision.objects.get_or_create(island=self.island, defaults={'current': 42})

    def test_test_database_is_sqlite(self):
        # Guard on the guard: if this ever runs on postgres the refusal below stops meaning
        # anything, and the test would pass for the wrong reason.
        self.assertEqual(connection.vendor, 'sqlite')

    def test_refuses_non_production_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'atlas-seed.db'
            with self.assertRaises(CommandError) as ctx:
                call_command('build_seed_db', '--output', str(output), stdout=StringIO())

            self.assertIn('Refusing', str(ctx.exception))
            self.assertFalse(output.exists(), 'no seed file should be produced when refusing')

    def test_allow_non_production_builds_with_a_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'atlas-seed.db'
            out = StringIO()
            call_command(
                'build_seed_db', '--output', str(output),
                '--allow-non-production', stdout=out,
            )

            self.assertTrue(output.exists())
            self.assertIn('build_seed_db', out.getvalue())

    def test_reports_the_cursors_it_stamped(self):
        """These numbers are what every install starts syncing from, so they have to be
        visible at build time rather than discovered in the field."""
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'atlas-seed.db'
            out = StringIO()
            call_command(
                'build_seed_db', '--output', str(output),
                '--allow-non-production', stdout=out,
            )

            printed = out.getvalue()
            self.assertIn('Seeded sync cursors', printed)
            self.assertIn(f'{self.island.key:12} 42', printed)
