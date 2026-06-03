"""Celery tasks for parish weather cache warming."""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name='weather.refresh_forecasts')
def refresh_forecasts_task(island_key: str | None = None) -> dict:
    from tenancy.models import Island
    from tenancy.services import for_island
    from weather.services import refresh_all_parishes

    islands = Island.objects.filter(is_live=True)
    if island_key:
        islands = islands.filter(key=island_key)

    totals: dict[str, int] = {}
    for island in islands:
        with for_island(island):
            count = refresh_all_parishes(island)
            totals[island.key] = count
            logger.info('weather.refresh_forecasts island=%s parishes=%s', island.key, count)

    return {'status': 'ok', 'refreshed': totals}
