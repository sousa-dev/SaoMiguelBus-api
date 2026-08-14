"""Celery tasks for the AzoresBus sync.

House shape (weather/tasks.py, atlas/tasks.py): explicit `name`, imports
deferred into the function body, loops live islands inside `for_island`, returns
a JSON-serialisable dict.
"""

from __future__ import annotations

import logging

from celery import shared_task
from decouple import config
from django.core.cache import cache


logger = logging.getLogger(__name__)

# One sync at a time, per 02 §4.6. The sampling sync is long, so the TTL is
# generous; a stuck run should block a second one rather than double the load.
SYNC_LOCK_KEY = 'azoresbus:sync:lock'
SYNC_LOCK_TTL = 45 * 60


def acquire_sync_lock() -> bool:
    """True if this caller now owns the sync lock."""
    return bool(cache.add(SYNC_LOCK_KEY, 'held', SYNC_LOCK_TTL))


def release_sync_lock() -> None:
    cache.delete(SYNC_LOCK_KEY)


def queue_sync(*, island_key: str | None = None, full: bool = False) -> dict:
    """Enqueue one sync run, or report why it was skipped.

    Lock-guarded so a rolling deploy, the lazy staleness backstop and the beat
    schedule cannot start three runs against a host with no published limit.
    """
    if not acquire_sync_lock():
        return {'queued': False, 'reason': 'another sync holds the lock'}

    try:
        result = sync_schedules_task.apply_async(
            kwargs={'island_key': island_key, 'full': full}, countdown=0,
        )
    except Exception:
        release_sync_lock()
        raise
    return {'queued': True, 'task_id': str(result.id), 'full': full}


@shared_task(name='azoresbus.sync_schedules')
def sync_schedules_task(island_key: str | None = None, full: bool = False) -> dict:
    from tenancy.models import Island
    from tenancy.services import for_island

    islands = Island.objects.filter(is_live=True)
    if island_key:
        islands = islands.filter(key=island_key)

    results: dict[str, str] = {}
    try:
        for island in islands:
            with for_island(island):
                logger.info('azoresbus.sync_schedules island=%s full=%s',
                            island.key, full)
                results[island.key] = 'pending'
    finally:
        release_sync_lock()

    return {'status': 'ok', 'islands': results, 'full': full}


@shared_task(name='azoresbus.sync_tariffs')
def sync_tariffs_task(island_key: str | None = None) -> dict:
    from tenancy.models import Island
    from tenancy.services import for_island
    from azoresbus.services_tariffs import TariffsError, sync_tariffs

    islands = Island.objects.filter(is_live=True)
    if island_key:
        islands = islands.filter(key=island_key)

    results: dict[str, str] = {}
    for island in islands:
        with for_island(island):
            try:
                outcome = sync_tariffs(island)
            except TariffsError as exc:
                logger.warning('tariffs sync failed island=%s: %s',
                               island.key, exc)
                results[island.key] = 'failed'
                continue
            results[island.key] = 'changed' if outcome['changed'] else 'unchanged'

    return {'status': 'ok', 'islands': results}


# -- lazy staleness backstop (02 §4.6) --------------------------------------

SYNC_STALE_DAYS = config('AZORESBUS_SYNC_STALE_DAYS', default=10, cast=int)


def maybe_queue_stale_sync(island) -> bool:
    """Enqueue a sync if the data is stale, and never delay the caller.

    Sits behind the read path as a backstop for the case where beat is not
    running at all -- a silent sync failure is the highest-likelihood way this
    whole thing goes wrong (02 §10). Lock-guarded, so concurrent searches
    enqueue exactly one run, and every failure is swallowed: a search must never
    fail because a background refresh could not be scheduled.
    """
    from datetime import timedelta

    from django.utils import timezone

    from azoresbus.models import SyncRun

    try:
        latest = (
            SyncRun.objects.filter(
                island=island,
                kind=SyncRun.KIND_SCHEDULES,
                status=SyncRun.STATUS_COMPLETED,
            )
            .order_by('-started_at')
            .first()
        )
        if latest is not None:
            age = timezone.now() - latest.started_at
            if age < timedelta(days=SYNC_STALE_DAYS):
                return False

        result = queue_sync(island_key=island.key, full=latest is None)
        return bool(result.get('queued'))
    except Exception:
        logger.exception('azoresbus staleness backstop failed to enqueue')
        return False
