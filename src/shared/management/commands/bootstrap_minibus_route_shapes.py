"""Queue minibus route shape harvest after deploy when shapes are missing."""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand

from minibus.services_route_shapes import any_line_missing_shapes, minibus_enabled
from tenancy.models import Island
from tenancy.services import for_island, get_or_create_default_island

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Queue minibus route shape harvest when any line is missing stored geometry.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--island',
            default='',
            help='Island key (default: DEFAULT_ISLAND_KEY or sao-miguel)',
        )

    def handle(self, *args, **options):
        island_key = (options['island'] or '').strip()
        if island_key:
            islands = [get_or_create_default_island(island_key)]
        else:
            islands = list(Island.objects.filter(is_live=True))

        queued: list[str] = []
        for island in islands:
            if not minibus_enabled(island):
                continue
            with for_island(island):
                if not any_line_missing_shapes(island):
                    continue
            try:
                from minibus.tasks import harvest_route_shapes_task

                async_result = harvest_route_shapes_task.delay(island_key=island.key)
                queued.append(f'{island.key}:{async_result.id}')
            except Exception:
                logger.exception('bootstrap_minibus_route_shapes failed island=%s', island.key)

        if queued:
            self.stdout.write(f'Queued minibus route shape harvest: {", ".join(queued)}')
        else:
            self.stdout.write('No minibus route shape harvest tasks queued.')
