"""Sync parish coordinates from bundled JSON and optionally reset proximity mappings."""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand

from tenancy.models import Island
from weather.models import Parish, ParishProximity


class Command(BaseCommand):
    help = (
        'Update Parish latitude/longitude from weather/data/parishes_sao_miguel.json. '
        'Use --reset-proximity to delete cached stop→parish mappings so they recompute.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--island',
            default='sao-miguel',
            help='Island key (default: sao-miguel)',
        )
        parser.add_argument(
            '--reset-proximity',
            action='store_true',
            help='Delete ParishProximity rows for this island after updating coordinates',
        )

    def handle(self, *args, **options):
        island_key = options['island']
        island = Island.objects.filter(key=island_key).first()
        if island is None:
            self.stderr.write(self.style.ERROR(f'Island not found: {island_key}'))
            return

        data_path = Path(__file__).resolve().parent.parent.parent / 'data' / 'parishes_sao_miguel.json'
        rows = json.loads(data_path.read_text(encoding='utf-8'))

        updated = 0
        for row in rows:
            parish, created = Parish.objects.update_or_create(
                island=island,
                slug=row['slug'],
                defaults={
                    'name': row['name'],
                    'concelho': row['concelho'],
                    'latitude': row['lat'],
                    'longitude': row['lon'],
                    'is_active': True,
                },
            )
            if created:
                updated += 1
            elif (
                parish.latitude != row['lat']
                or parish.longitude != row['lon']
                or parish.name != row['name']
                or parish.concelho != row['concelho']
            ):
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Synced {len(rows)} parishes for {island_key} ({updated} created/updated)',
            ),
        )

        if options['reset_proximity']:
            deleted, _ = ParishProximity.objects.filter(island=island).delete()
            self.stdout.write(
                self.style.WARNING(f'Deleted {deleted} ParishProximity row(s) for {island_key}'),
            )
