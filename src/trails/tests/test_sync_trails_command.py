"""The sync_trails command must route each island to its own provider."""
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from trails.models import Trail


class SyncTrailsCommandTests(TestCase):
    def test_madeira_island_is_accepted_and_imports_official_routes(self):
        out = StringIO()
        call_command('sync_trails', '--island', 'madeira', stdout=out)
        self.assertEqual(Trail.objects.filter(island__key='madeira').count(), 37)
        self.assertIn('trails_created', out.getvalue())

    def test_removals_reach_the_command_output(self):
        """A run that deletes rows must say so, not report only creations."""
        from unittest.mock import patch
        out = StringIO()
        with patch('trails.services.sync_open_data_for_island', return_value={
            'trails_created': 0, 'trails_updated': 3, 'trails_removed': 2,
            'pois_created': 0, 'pois_updated': 0, 'skipped': 0,
        }):
            call_command('sync_trails', '--island', 'madeira', stdout=out)
        self.assertIn("'trails_removed': 2", out.getvalue())

    def test_island_with_no_registered_provider_is_rejected(self):
        with self.assertRaises(CommandError) as ctx:
            call_command('sync_trails', '--island', 'desertas')
        self.assertIn('desertas', str(ctx.exception))
