"""Compare compat endpoints against legacy DB counts."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import urlparse

from django.core.management.base import BaseCommand

from tenancy.services import for_island, get_or_create_default_island
from transit.models import DATASET_LEGACY, Stop, Trip


class Command(BaseCommand):
    help = 'Validate migrated data counts against legacy SQLite'

    def add_arguments(self, parser):
        parser.add_argument(
            '--legacy-db',
            default='sqlite:///../legacy/src/db.sqlite3',
        )
        parser.add_argument('--island', default='sao-miguel')
        parser.add_argument('--sample-size', type=int, default=100)

    def handle(self, *args, **options):
        island = get_or_create_default_island(options['island'])
        legacy_path = self._sqlite_path(options['legacy_db'])
        legacy_stops = self._count_legacy(legacy_path, 'app_stop')
        legacy_routes = self._count_legacy(legacy_path, 'app_route')

        with for_island(island):
            # Unfiltered counts fail permanently the day AzoresBus lands.
            new_stops = Stop.objects.filter(dataset=DATASET_LEGACY).count()
            new_trips = Trip.objects.filter(dataset=DATASET_LEGACY).count()

        self.stdout.write(f'Legacy stops: {legacy_stops} | New stops: {new_stops}')
        self.stdout.write(f'Legacy routes: {legacy_routes} | New trips: {new_trips}')

        if legacy_stops != new_stops:
            self.stderr.write(self.style.ERROR('Stop count mismatch'))
            raise SystemExit(1)
        if legacy_routes != new_trips:
            self.stderr.write(self.style.ERROR('Route/trip count mismatch'))
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS('Parity check passed'))

    def _sqlite_path(self, url: str) -> Path:
        raw = url.replace('sqlite:///', '', 1)
        path = Path(raw)
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        return path

    def _count_legacy(self, path: Path, table: str) -> int:
        conn = sqlite3.connect(path)
        try:
            return conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
        finally:
            conn.close()
