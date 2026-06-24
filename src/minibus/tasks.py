"""Celery tasks for minibus route shape harvest."""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name='minibus.harvest_route_shapes')
def harvest_route_shapes_task(island_key: str | None = None, *, force: bool = False) -> dict:
    from minibus.services_route_shapes import any_line_missing_shapes, harvest_route_shapes, minibus_enabled
    from tenancy.models import Island
    from tenancy.services import for_island

    islands = Island.objects.filter(is_live=True)
    if island_key:
        islands = islands.filter(key=island_key)

    reports: dict[str, dict] = {}
    for island in islands:
        if not minibus_enabled(island):
            reports[island.key] = {'status': 'skipped', 'reason': 'minibus_disabled'}
            continue
        if not force and not any_line_missing_shapes(island):
            reports[island.key] = {'status': 'ok', 'skipped_all': True}
            continue
        with for_island(island):
            report = harvest_route_shapes(island, force=force)
            reports[island.key] = report
            logger.info(
                'minibus.harvest_route_shapes island=%s harvested=%s missing=%s',
                island.key,
                report.get('harvested'),
                report.get('missing'),
            )

    return {'status': 'ok', 'islands': reports}
