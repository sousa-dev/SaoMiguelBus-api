"""Traffic Celery tasks."""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name='traffic.run_lifecycle')
def run_lifecycle_task() -> dict:
    from traffic.services import run_lifecycle

    counts = run_lifecycle()
    logger.info('traffic.run_lifecycle counts=%s', counts)
    return {'status': 'ok', **counts}
