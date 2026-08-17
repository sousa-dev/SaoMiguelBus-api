"""Deploy bootstrap feed sync command tests."""

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from shared.feed_syncs import enabled_feed_labels
from tenancy.models import Island
from tenancy.services import get_or_create_default_island


class BootstrapFeedSyncsTestCase(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        self.island.is_live = True
        self.island.feature_flags = {
            **(self.island.feature_flags or {}),
            'news': True,
            'seismic': True,
            'trails': True,
        }
        self.island.save()

    def test_enabled_feed_labels_includes_all_external_modules(self):
        labels = enabled_feed_labels()
        self.assertEqual(labels, ['news', 'seismic', 'trails'])

    def test_enabled_feed_labels_omits_disabled_modules(self):
        # enabled_feed_labels() is archipelago-wide — a feed is refreshed on deploy when *any*
        # live island enables it. Since tenancy/0020 turns trails on for all nine seeded
        # islands, disabling a module has to be done everywhere for it to drop out.
        for island in Island.objects.filter(is_live=True):
            island.feature_flags = {
                **(island.feature_flags or {}),
                'news': island.key == self.island.key,
                'seismic': False,
                'trails': False,
            }
            island.save(update_fields=['feature_flags'])
        self.assertEqual(enabled_feed_labels(), ['news'])

    def test_enabled_feed_labels_spans_islands(self):
        """A module enabled on any live island keeps its feed in the deploy refresh, even when
        the default island has it off — this is what carries the eight atlas islands' trails."""
        self.island.feature_flags = {
            **(self.island.feature_flags or {}),
            'news': True,
            'seismic': False,
            'trails': False,
        }
        self.island.save(update_fields=['feature_flags'])

        other = Island.objects.filter(is_live=True).exclude(key=self.island.key).first()
        assert other is not None
        other.feature_flags = {**(other.feature_flags or {}), 'trails': True}
        other.save(update_fields=['feature_flags'])

        self.assertEqual(enabled_feed_labels(), ['news', 'trails'])

    @patch('shared.management.commands.bootstrap_feed_syncs.queue_feed_sync')
    def test_bootstrap_command_queues_enabled_feeds(self, mock_queue):
        mock_queue.side_effect = [
            {'task': 'news.poll_sources', 'celery_task_id': 'a'},
            {'task': 'seismic.sync_events', 'celery_task_id': 'b'},
            {'task': 'trails.sync_open_data', 'celery_task_id': 'c'},
        ]
        out = StringIO()
        call_command('bootstrap_feed_syncs', stdout=out)
        self.assertEqual(mock_queue.call_count, 3)
        output = out.getvalue()
        self.assertIn('news.poll_sources', output)
        self.assertIn('trails.sync_open_data', output)
