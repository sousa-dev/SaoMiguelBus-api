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

from azoresbus.models import SyncRun, TariffSnapshot
from azoresbus.tasks import queue_sync, queue_tariffs
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
        """Sync what is missing. Schedules and tariffs are independent."""
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

        needs_schedules = force or not self._has_schedules(island)
        needs_tariffs = force or not self._has_tariffs(island)

        if not needs_schedules and not needs_tariffs:
            self.stdout.write(
                f'[{island.key}] schedules and tariffs are up to date; '
                'nothing queued.'
            )
            return

        if needs_schedules:
            # run_sync fetches tariffs as a step, so queueing both would fetch
            # them twice.
            self._queue(
                island, queue_sync, 'full AzoresBus sync (schedules + tariffs)',
                island_key=island.key, full=True,
            )
            return

        self._queue(
            island, queue_tariffs, 'tariffs refresh', island_key=island.key,
        )

    def _queue(self, island: Island, fn, label: str, **kwargs) -> None:
        try:
            result = fn(**kwargs)
        except Exception:
            # A broker outage must never fail a deploy, exactly as
            # bootstrap_feed_syncs treats it.
            logger.exception('bootstrap_azoresbus could not queue %s', label)
            self.stdout.write(self.style.WARNING(
                f'[{island.key}] could not queue the {label} (broker down?); '
                'the lazy staleness backstop will retry on first search.'
            ))
            return

        if result.get('queued'):
            self.stdout.write(self.style.SUCCESS(
                f'[{island.key}] queued the {label} '
                f'(task {result.get("task_id")}).'
            ))
        else:
            self.stdout.write(
                f'[{island.key}] {label} not queued: {result.get("reason")}.'
            )

    def _has_schedules(self, island: Island) -> bool:
        """Data alone is not enough -- a half-import is worse than none."""
        with for_island(island):
            return (
                Trip.objects.filter(
                    island=island, dataset=DATASET_AZORESBUS,
                ).exists()
                and SyncRun.objects.filter(
                    island=island,
                    kind=SyncRun.KIND_SCHEDULES,
                    status=SyncRun.STATUS_COMPLETED,
                ).exists()
            )

    def _has_tariffs(self, island: Island) -> bool:
        with for_island(island):
            return TariffSnapshot.objects.filter(
                island=island, is_current=True,
            ).exists()
