"""Seismic Celery tasks."""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name='seismic.sync_events')
def sync_events_task(island_key: str | None = None) -> dict:
    from seismic.services import sync_all_events

    totals = sync_all_events(island_key=island_key)
    logger.info('seismic.sync_events island=%s totals=%s', island_key, totals)
    return {'status': 'ok', **totals}
