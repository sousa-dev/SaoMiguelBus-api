"""SyncRun.request_count must update WHILE a run is in flight, not only at the
end.

Found the hard way: a real production run sat at `status=Running,
request_count=0` for its entire ~13 minute duration, and there was no way to
tell a healthy run from an orphaned one (a worker that died mid-run leaves the
row stuck at Running forever, since nothing is left alive to write the final
update). `request_count` was only ever written once, in run_sync's success and
failure branches -- never during `_fetch_all`'s ~2000-request loop.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from azoresbus.models import SyncRun
from azoresbus.services_sync import _fetch_all
from tenancy.services import get_or_create_default_island


class ProgressCheckpointTests(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        self.run = SyncRun.objects.create(
            island=self.island, kind=SyncRun.KIND_SCHEDULES,
        )

    def _client(self, responses):
        client = MagicMock()
        client.request_count = 0

        def get_json(path):
            client.request_count += 1
            return responses(path)

        client.get_json.side_effect = get_json
        return client

    def test_request_count_advances_in_the_db_before_the_fetch_finishes(self):
        seen_mid_call = {}

        def responses(path):
            if path == '/stops':
                return []
            if path == '/routes?active=true&passengerInfo=true':
                return [{'id': '1'}, {'id': '2'}]
            if 'journeys?day=' in path:
                # After route 1's listings are done, the DB row must already
                # reflect requests made so far -- not still show 0.
                if 'routes/1/journeys' in path and '2026-09-15' in path:
                    seen_mid_call['count'] = (
                        SyncRun.objects.get(pk=self.run.pk).request_count
                    )
                return []
            return {}

        client = self._client(responses)
        _fetch_all(client, [__import__('datetime').date(2026, 9, 14),
                            __import__('datetime').date(2026, 9, 15)],
                  run=self.run)

        self.assertGreater(
            seen_mid_call.get('count', 0), 0,
            'request_count in the DB was still 0 partway through the fetch',
        )
        self.assertLess(
            seen_mid_call['count'], client.request_count,
            'the mid-call checkpoint should be a partial count, not the final one',
        )

    def test_final_db_count_matches_the_client_after_a_full_fetch(self):
        def responses(path):
            if path == '/stops':
                return []
            if path == '/routes?active=true&passengerInfo=true':
                return [{'id': '1'}]
            return []

        client = self._client(responses)
        _fetch_all(client, [__import__('datetime').date(2026, 9, 14)],
                  run=self.run)

        self.run.refresh_from_db()
        self.assertEqual(self.run.request_count, client.request_count)

    def test_fetch_without_a_run_still_works(self):
        """run is optional -- callers that don't care about live progress
        (e.g. a --dry-run path that never calls this) must not be forced to
        pass one."""
        def responses(path):
            if path == '/stops':
                return []
            if path == '/routes?active=true&passengerInfo=true':
                return []
            return []

        client = self._client(responses)
        result = _fetch_all(client, [], run=None)
        self.assertIn('stops', result)


class FailurePreservesLastCheckpointTests(TestCase):
    """A run that fails must not wipe the progress it made before failing.

    Otherwise the one moment you most want to see "how far did it get before
    it broke" is exactly when the field goes blank.
    """

    def test_stats_after_a_failed_run_still_shows_the_last_phase(self):
        from unittest.mock import patch as _patch

        from azoresbus.client import AzoresbusError
        from azoresbus.services_sync import run_sync
        from transit.models import Holiday
        from datetime import date

        island = get_or_create_default_island()
        Holiday.objects.get_or_create(
            island=island, date=date(2026, 12, 25), defaults={'name': 'Natal'},
        )

        # run_sync imports AzoresbusClient locally from azoresbus.client at
        # call time, so that is the module to patch, not services_sync.
        with _patch('azoresbus.client.AzoresbusClient') as mock_client_cls:
            client = MagicMock()
            client.request_count = 42

            def fail_after_checkpoint(*args, **kwargs):
                # Simulate: routes fetched fine (checkpoint written), then the
                # listing loop dies partway through.
                run = SyncRun.objects.filter(
                    island=island, kind=SyncRun.KIND_SCHEDULES,
                ).latest('started_at')
                SyncRun.objects.filter(pk=run.pk).update(
                    request_count=42,
                    stats={'phase': 'listings', 'phase_progress': '12/55'},
                )
                raise AzoresbusError('upstream timed out')

            client.get_json.side_effect = fail_after_checkpoint
            mock_client_cls.return_value = client

            with self.assertRaises(Exception):
                run_sync(island, dates=[date(2026, 9, 14)])

        run = SyncRun.objects.filter(
            island=island, kind=SyncRun.KIND_SCHEDULES,
        ).latest('started_at')
        self.assertEqual(run.status, SyncRun.STATUS_PARTIAL)
        self.assertEqual(
            run.stats.get('phase'), 'listings',
            'the last checkpoint was overwritten instead of preserved',
        )
        self.assertTrue(run.error)
