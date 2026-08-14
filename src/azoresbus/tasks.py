"""Celery tasks for the AzoresBus sync.

House shape (weather/tasks.py, atlas/tasks.py): explicit `name`, imports
deferred into the function body, loops live islands inside `for_island`, returns
a JSON-serialisable dict.
"""

from __future__ import annotations

import logging

from celery import shared_task
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
    logger.info('azoresbus.sync_tariffs island=%s', island_key)
    return {'status': 'ok'}
