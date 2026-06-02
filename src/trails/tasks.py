"""Trails Celery tasks."""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name='trails.sync_open_data')
def sync_open_data_task(island_key: str | None = None) -> dict:
    from trails.services import sync_all_open_data

    totals = sync_all_open_data(island_key=island_key)
    logger.info('trails.sync_open_data island=%s totals=%s', island_key, totals)
    return {'status': 'ok', **totals}
