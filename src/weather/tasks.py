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
    failed: dict[str, str] = {}
    for island in islands:
        # One island's upstream failure must not cost the others their cache. Island
        # ordering is by name, so 'Madeira' is refreshed before 'São Miguel' — without this
        # guard a single Open-Meteo error on the Madeira batch left the shipped product's
        # forecasts unwarmed for the hour, and the task looked like it had simply failed.
        try:
            with for_island(island):
                count = refresh_all_parishes(island)
        except Exception as exc:
            logger.exception('weather.refresh_forecasts failed island=%s', island.key)
            failed[island.key] = str(exc)
            continue
        totals[island.key] = count
        logger.info('weather.refresh_forecasts island=%s parishes=%s', island.key, count)

    return {'status': 'partial' if failed else 'ok', 'refreshed': totals, 'failed': failed}
