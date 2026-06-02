"""Feed sync registry — shared by bootstrap command and ops HTTP triggers."""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

FeedRunner = Callable[[str | None], dict[str, Any]]

FEED_LABELS: tuple[str, ...] = ('news', 'seismic', 'trails')

FEED_TASK_NAMES: dict[str, str] = {
    'news': 'news.poll_sources',
    'seismic': 'seismic.sync_events',
    'trails': 'trails.sync_open_data',
}


def _run_news(island_key: str | None) -> dict[str, Any]:
    from news.services import poll_all_sources

    return {'status': 'ok', **poll_all_sources(island_key=island_key)}


def _run_seismic(island_key: str | None) -> dict[str, Any]:
    from seismic.services import sync_all_events

    return {'status': 'ok', **sync_all_events(island_key=island_key)}


def _run_trails(island_key: str | None) -> dict[str, Any]:
    from trails.services import sync_all_open_data

    return {'status': 'ok', **sync_all_open_data(island_key=island_key)}


FEED_RUNNERS: dict[str, FeedRunner] = {
    'news': _run_news,
    'seismic': _run_seismic,
    'trails': _run_trails,
}


def _queue_news(island_key: str | None):
    from news.tasks import poll_sources_task

    return poll_sources_task.delay(island_key=island_key)


def _queue_seismic(island_key: str | None):
    from seismic.tasks import sync_events_task

    return sync_events_task.delay(island_key=island_key)


def _queue_trails(island_key: str | None):
    from trails.tasks import sync_open_data_task

    return sync_open_data_task.delay(island_key=island_key)


FEED_QUEUERS = {
    'news': _queue_news,
    'seismic': _queue_seismic,
    'trails': _queue_trails,
}


def normalize_feed_param(feed: str) -> list[str]:
    value = (feed or 'all').strip().lower()
    if value == 'all':
        return list(FEED_LABELS)
    if value in FEED_LABELS:
        return [value]
    raise ValueError(f'Unknown feed {feed!r}; use all or one of {", ".join(FEED_LABELS)}')


def run_feed_sync(label: str, *, island_key: str | None = None) -> dict[str, Any]:
    runner = FEED_RUNNERS[label]
    return runner(island_key)


def queue_feed_sync(label: str, *, island_key: str | None = None) -> dict[str, Any]:
    async_result = FEED_QUEUERS[label](island_key)
    return {
        'task': FEED_TASK_NAMES[label],
        'celery_task_id': async_result.id,
    }


def trigger_feed_syncs(
    labels: list[str],
    *,
    island_key: str | None = None,
    run_async: bool = False,
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for label in labels:
        try:
            if run_async:
                queued = queue_feed_sync(label, island_key=island_key)
                results[label] = {'ok': True, 'mode': 'async', **queued}
            else:
                payload = run_feed_sync(label, island_key=island_key)
                results[label] = {'ok': True, 'mode': 'sync', **payload}
        except Exception as exc:
            logger.exception('feed sync failed label=%s island=%s', label, island_key)
            results[label] = {
                'ok': False,
                'mode': 'async' if run_async else 'sync',
                'task': FEED_TASK_NAMES.get(label),
                'error': str(exc),
                'error_type': type(exc).__name__,
            }
    return results
