"""Recompute parish assignment for every atlas POI/trail — initial pass or a parish-boundary
revision (SDD 02 §3.3)."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from atlas.services import backfill_parishes
from tenancy.models import Island


class Command(BaseCommand):
    help = 'Recompute AtlasPoi/AtlasTrail parish_slug for one island.'

    def add_arguments(self, parser):
        parser.add_argument('--island', required=True, help='Island key, e.g. sao-miguel')

    def handle(self, *args, **options):
        island = Island.objects.filter(key=options['island']).first()
        if island is None:
            raise CommandError(f'Island not found: {options["island"]}')

        updated = backfill_parishes(island)
        self.stdout.write(self.style.SUCCESS(f'backfill_atlas_parishes island={island.key}: {updated} rows'))
