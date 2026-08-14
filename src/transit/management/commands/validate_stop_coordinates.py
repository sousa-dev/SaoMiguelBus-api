"""Validate transit stop coordinates for an island."""

from __future__ import annotations

import sys

from django.core.management.base import BaseCommand

from shared.geo import is_within_island_radius
from tenancy.models import Island
from transit.models import Stop


class Command(BaseCommand):
    help = 'Report transit stops with missing or out-of-island coordinates.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--island',
            default='sao-miguel',
            help='Island key (default: sao-miguel)',
        )

    def handle(self, *args, **options):
        island_key = options['island']
        island = Island.objects.filter(key=island_key).first()
        if island is None:
            self.stderr.write(self.style.ERROR(f'Island not found: {island_key}'))
            sys.exit(1)

        # Dataset-agnostic on purpose: this is a data-quality sweep and every
        # stop in every network should sit inside the island radius.
        invalid: list[str] = []
        for stop in Stop.objects.filter(island=island).order_by('name'):
            if not is_within_island_radius(
                stop.latitude,
                stop.longitude,
                center_lat=island.center_lat,
                center_lng=island.center_lng,
                radius_km=island.radius_km,
            ):
                invalid.append(
                    f'{stop.name} (id={stop.pk}): ({stop.latitude}, {stop.longitude})',
                )

        if invalid:
            self.stderr.write(
                self.style.ERROR(
                    f'{len(invalid)} invalid stop coordinate(s) on {island_key}:',
                ),
            )
            for row in invalid:
                self.stderr.write(f'  - {row}')
            sys.exit(1)

        count = Stop.objects.filter(island=island).count()
        self.stdout.write(
            self.style.SUCCESS(
                f'All {count} stop(s) on {island_key} have valid coordinates.',
            ),
        )
