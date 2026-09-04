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


def queue_tariffs(*, island_key: str | None = None) -> dict:
    """Enqueue a tariffs-only refresh. One conditional request.

    Not lock-guarded: it is cheap, idempotent and independent of the schedule
    lock, so a fare refresh must never be blocked by a 13-minute sync.
    """
    result = sync_tariffs_task.apply_async(
        kwargs={'island_key': island_key}, countdown=0,
    )
    return {'queued': True, 'task_id': str(result.id)}


@shared_task(name='azoresbus.sync_schedules')
def sync_schedules_task(island_key: str | None = None, full: bool = False) -> dict:
    """Run a real sync. Same code path as `manage.py sync_azoresbus`.

    Scoped to the islands AzoresBus actually serves: the other eight Azorean
    tenants are live but have no AzoresBus data and never will, and syncing them
    would spend the request budget on nothing.
    """
    from tenancy.models import Island
    from tenancy.services import for_island
    from azoresbus.services_sync import SyncAborted, run_sync

    from azoresbus.management.commands.bootstrap_azoresbus import (
        AZORESBUS_ISLANDS,
    )

    from azoresbus.services_sync import reclaim_stale_runs

    keys = [island_key] if island_key else AZORESBUS_ISLANDS
    islands = Island.objects.filter(is_live=True, key__in=keys)

    results: dict[str, dict | str] = {}
    try:
        for island in islands:
            with for_island(island):
                # Age-based, not all_running: a sync genuinely in flight on
                # another worker must never be killed by this one. Anything
                # older than the lock's own TTL cannot still be alive.
                reclaim_stale_runs(island)
                try:
                    results[island.key] = run_sync(island, full=full)
                except SyncAborted as exc:
                    logger.warning('azoresbus sync aborted island=%s: %s',
                                   island.key, exc)
                    results[island.key] = f'aborted: {exc}'
                except Exception:
                    logger.exception('azoresbus sync failed island=%s',
                                     island.key)
                    results[island.key] = 'failed'
    finally:
        # Always release, or a crashed run wedges every later trigger for 45min.
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


# -- iOS Live Activity push (Uber-style live trip bar) ----------------------

PUSH_LOCK_KEY = 'azoresbus:live_activity_push:lock'
# Well under the beat interval (60s): a run that is genuinely stuck should
# not block every later tick for its full TTL, only the ones that would have
# overlapped it.
PUSH_LOCK_TTL = 50


@shared_task(name='azoresbus.push_live_activities')
def push_live_activities_task() -> dict:
    """Keeps every registered iOS Live Activity fresh.

    Beat-scheduled roughly once a minute (migration
    `0004_periodic_task_live_activities`). Reuses `live_for_trips` -- the same
    join `/api/v3/azoresbus/trips/live` uses -- rather than re-deriving which
    vehicle is running which trip a second time.
    """
    from django.utils import timezone

    from azoresbus.apns import (
        EVENT_END,
        EVENT_UPDATE,
        ApnsError,
        live_activity_payload,
        push_live_activity,
    )
    from azoresbus.models import LiveActivityRegistration
    from azoresbus.services_live_activity_push import (
        current_leg,
        has_finished,
        snapshot_from_live_row,
    )
    from azoresbus.services_trip_live import live_for_trips
    from tenancy.models import Island
    from tenancy.services import for_island

    if not cache.add(PUSH_LOCK_KEY, 'held', PUSH_LOCK_TTL):
        return {'status': 'skipped', 'reason': 'another run holds the lock'}

    pushed = 0
    ended = 0
    failed = 0

    try:
        now = timezone.now()
        for island in Island.objects.filter(is_live=True):
            with for_island(island):
                registrations = list(
                    LiveActivityRegistration.objects.filter(
                        island=island, ended_at__isnull=True,
                    )
                )
                if not registrations:
                    continue

                trip_ids = sorted({
                    leg['tripId'] for reg in registrations for leg in reg.legs
                })
                rows_by_trip: dict[int, dict] = {}
                if trip_ids:
                    try:
                        rows_by_trip = {
                            row['tripId']: row for row in live_for_trips(island, trip_ids)
                        }
                    except Exception:
                        logger.exception(
                            'live_for_trips failed during live-activity push island=%s',
                            island.key,
                        )

                for registration in registrations:
                    leg = current_leg(registration.legs, now)
                    if leg is None:
                        continue

                    finished = has_finished(registration.legs, now)
                    snapshot = snapshot_from_live_row(leg, rows_by_trip.get(leg['tripId']), now)
                    if finished:
                        snapshot['state'] = 'completed'

                    payload = live_activity_payload(
                        snapshot,
                        event=EVENT_END if finished else EVENT_UPDATE,
                        # A few minutes' grace before the card actually
                        # disappears, so "trip finished" is legible rather
                        # than the card vanishing mid-glance.
                        dismiss_in_seconds=5 * 60,
                    )
                    try:
                        push_live_activity(registration.push_token, registration.environment, payload)
                    except ApnsError as exc:
                        failed += 1
                        registration.failure_count += 1
                        if exc.terminal:
                            registration.ended_at = now
                        registration.save(update_fields=['failure_count', 'ended_at'])
                        continue

                    registration.last_pushed_at = now
                    if finished:
                        registration.ended_at = now
                        ended += 1
                    else:
                        pushed += 1
                    registration.save(update_fields=['last_pushed_at', 'ended_at'])
    finally:
        cache.delete(PUSH_LOCK_KEY)

    return {'status': 'ok', 'pushed': pushed, 'ended': ended, 'failed': failed}


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
