"""News Celery tasks."""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name='news.poll_sources')
def poll_sources_task(island_key: str | None = None) -> dict:
    from news.services import poll_all_sources

    totals = poll_all_sources(island_key=island_key)
    logger.info('news.poll_sources island=%s totals=%s', island_key, totals)
    return {'status': 'ok', **totals}
