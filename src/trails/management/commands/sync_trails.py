"""Sync Visit Azores trails into one island, or every island with the trails flag.

Re-runnable and idempotent: trails upsert on (island, source_ref), so a failed run can simply
be repeated. Wraps the same trails.services.sync_all_open_data() the nightly
trails.sync_open_data Celery task calls — no separate sync path to drift.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from tenancy.models import Island
from trails.services import sync_all_open_data
from trails.visitazores_sync import VISITAZORES_ISLAND_SLUGS


class Command(BaseCommand):
    help = (
        'Sync official Visit Azores trails into one island (--island pico) '
        'or every island with the trails feature flag (--all).'
    )

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument('--island', help='Island key, e.g. pico')
        group.add_argument(
            '--all',
            action='store_true',
            dest='all_islands',
            help='Every island with feature_flags.trails enabled.',
        )

    def handle(self, *args, **options):
        island_key = options.get('island')

        if island_key:
            island = Island.objects.filter(key=island_key).first()
            if island is None:
                raise CommandError(f'Island not found: {island_key}')
            if island.key not in VISITAZORES_ISLAND_SLUGS:
                raise CommandError(
                    f'No Visit Azores listing slug registered for {island.key}. '
                    f'Known: {", ".join(sorted(VISITAZORES_ISLAND_SLUGS))}',
                )

        # A single-island run passes island_key straight through, which deliberately bypasses
        # the feature-flag filter in _islands_for_sync — useful for dry-running an island
        # before its flag is switched on.
        totals = sync_all_open_data(island_key=island_key)

        if totals['islands'] == 0:
            self.stdout.write(
                self.style.WARNING('sync_trails matched no islands (is feature_flags.trails set?)'),
            )
            return

        style = self.style.WARNING if totals.get('failed_islands') else self.style.SUCCESS
        self.stdout.write(
            style(f'sync_trails island={island_key or "*"}: {totals}'),
        )
