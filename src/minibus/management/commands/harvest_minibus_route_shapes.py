"""Harvest PDL Mini Bus route polylines from Eleven Systems AVL."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from minibus.services_route_shapes import harvest_route_shapes, minibus_enabled
from tenancy.services import for_island, get_or_create_default_island


class Command(BaseCommand):
    help = 'Harvest minibus route polylines from live AVL when shapes are missing.'

    def add_arguments(self, parser):
        parser.add_argument('--island', default='sao-miguel', help='Island key (default: sao-miguel)')
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-harvest even when route shapes already exist',
        )
        parser.add_argument(
            '--sync',
            action='store_true',
            help='Run synchronously instead of queueing Celery',
        )

    def handle(self, *args, **options):
        island_key = options['island']
        island = get_or_create_default_island(island_key)

        if not minibus_enabled(island):
            self.stdout.write(f'Minibus disabled for island {island_key}; nothing to do.')
            return

        if options['sync']:
            with for_island(island):
                report = harvest_route_shapes(island, force=options['force'])
            self.stdout.write(str(report))
            return

        from minibus.tasks import harvest_route_shapes_task

        async_result = harvest_route_shapes_task.delay(
            island_key=island_key,
            force=options['force'],
        )
        self.stdout.write(
            f'Queued minibus.harvest_route_shapes for {island_key} (task_id={async_result.id})',
        )
