"""Queue the initial AzoresBus schedule sync after deploy.

Runs from `runserver.sh` alongside bootstrap_atlas and bootstrap_feed_syncs, so
the first deployment after the changeover lands populates itself with no manual
step.

Never from AppConfig.ready(): runserver.sh ends with `gunicorn --workers 3`, and
celery worker and beat load the app too, so a ready() hook would fire ~5 times
concurrently and block startup for the length of a full sync.
"""

from __future__ import annotations

import logging

from decouple import config
from django.core.management.base import BaseCommand

from azoresbus.models import SyncRun
from azoresbus.tasks import queue_sync
from tenancy.models import Island
from tenancy.services import for_island
from transit.models import DATASET_AZORESBUS, Trip

logger = logging.getLogger(__name__)

# AzoresBus is a Sao Miguel concession. The other eight Azorean islands are live
# tenants with no AzoresBus data and never will have any, so bootstrapping them
# would queue eight pointless full syncs against a rate-limited host.
AZORESBUS_ISLANDS = [
    key.strip()
    for key in config('AZORESBUS_ISLANDS', default='sao-miguel').split(',')
    if key.strip()
]


class Command(BaseCommand):
    help = 'Queue an AzoresBus sync if the new network has no usable data yet.'

    def add_arguments(self, parser) -> None:
        parser.add_argument('--island', dest='island_key', default='',
                            help='Limit to one island key. Default: all live.')
        parser.add_argument('--force', action='store_true',
                            help='Queue a run regardless of current state.')

    def handle(self, *args, **options) -> None:
        island_key = (options.get('island_key') or '').strip()
        force = bool(options.get('force'))

        keys = [island_key] if island_key else AZORESBUS_ISLANDS
        islands = Island.objects.filter(is_live=True, key__in=keys)

        if not islands:
            self.stdout.write(
                f'No live island matches {keys}; nothing to bootstrap.'
            )
            return

        for island in islands:
            self._bootstrap(island, force=force)

    def _bootstrap(self, island: Island, *, force: bool) -> None:
        # Every worker has just restarted, so any Running row belongs to a
        # process that no longer exists -- and its un-released lock would
        # otherwise block this very sync for the lock's full 45-minute TTL.
        # This is the deploy recovering from its own previous kill.
        from azoresbus.services_sync import reclaim_stale_runs

        reclaimed = reclaim_stale_runs(island, all_running=True)
        if reclaimed:
            self.stdout.write(self.style.WARNING(
                f'[{island.key}] reclaimed {reclaimed} orphaned sync run(s) '
                'left Running by a killed worker; lock released.'
            ))

        if not force and self._has_usable_data(island):
            self.stdout.write(
                f'[{island.key}] AzoresBus data is up to date; nothing queued.'
            )
            return

        try:
            result = queue_sync(island_key=island.key, full=True)
        except Exception:
            # A broker outage must never fail a deploy, exactly as
            # bootstrap_feed_syncs treats it.
            logger.exception('bootstrap_azoresbus could not queue a sync')
            self.stdout.write(self.style.WARNING(
                f'[{island.key}] could not queue the sync (broker down?); '
                'the lazy staleness backstop will retry on first search.'
            ))
            return

        if result.get('queued'):
            self.stdout.write(self.style.SUCCESS(
                f'[{island.key}] queued a full AzoresBus sync '
                f'(task {result.get("task_id")}).'
            ))
        else:
            self.stdout.write(
                f'[{island.key}] not queued: {result.get("reason")}.'
            )

    def _has_usable_data(self, island: Island) -> bool:
        """Data alone is not enough -- a half-import is worse than none."""
        with for_island(island):
            has_trips = Trip.objects.filter(
                island=island, dataset=DATASET_AZORESBUS,
            ).exists()
            has_success = SyncRun.objects.filter(
                island=island,
                kind=SyncRun.KIND_SCHEDULES,
                status=SyncRun.STATUS_COMPLETED,
            ).exists()
        return has_trips and has_success
