"""`manage.py import_atlas` argument handling.

--all-islands exists so runserver.sh can reconcile every island on deploy without hardcoding
nine invocations. It runs under `set -e`, so per-island failure containment matters here.
"""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import TestCase

from atlas.models import AtlasTrail
from tenancy.models import Island
from trails.models import Trail


def _make_trail(island: Island, source_ref: str) -> Trail:
    return Trail.objects.create(
        island=island,
        source_ref=source_ref,
        name=f'Trail {source_ref}',
        start_lat=38.58,
        start_lon=-28.72,
        geojson={'type': 'LineString', 'coordinates': [[-28.72, 38.58], [-28.71, 38.585]]},
    )


class ImportAtlasCommandTestCase(TestCase):
    def test_requires_island_or_all_islands(self):
        with self.assertRaises(CommandError):
            call_command('import_atlas', '--source', 'trails', stdout=StringIO())

    def test_island_and_all_islands_are_mutually_exclusive(self):
        with self.assertRaises(CommandError):
            call_command(
                'import_atlas', '--source', 'trails',
                '--island', 'faial', '--all-islands', stdout=StringIO(),
            )

    def test_unknown_island_errors(self):
        with self.assertRaises(CommandError):
            call_command('import_atlas', '--source', 'trails', '--island', 'atlantis', stdout=StringIO())

    def test_all_islands_imports_every_atlas_island(self):
        _make_trail(Island.objects.get(key='faial'), 'PRC4FAI')
        _make_trail(Island.objects.get(key='pico'), 'PR9PIC')

        out = StringIO()
        call_command('import_atlas', '--source', 'trails', '--all-islands', stdout=out)

        self.assertEqual(AtlasTrail.objects.unscoped().count(), 2)
        self.assertIn('islands ok', out.getvalue())

    def test_one_island_failing_does_not_abort_the_rest(self):
        """Deploy-path behaviour: runserver.sh runs this under `set -e`, so a single bad
        island must not take the other eight — or the deploy — down with it."""
        _make_trail(Island.objects.get(key='faial'), 'PRC4FAI')
        calls = {'n': 0}
        real_run = None

        def flaky(self):
            calls['n'] += 1
            if calls['n'] == 1:
                raise RuntimeError('boom')
            return real_run(self)

        from atlas.importers.trails import TrailsImporter

        real_run = TrailsImporter.run
        out, err = StringIO(), StringIO()
        with patch.object(TrailsImporter, 'run', flaky):
            call_command('import_atlas', '--source', 'trails', '--all-islands', stdout=out, stderr=err)

        self.assertIn('failed', err.getvalue())
        self.assertIn('islands ok', out.getvalue())
