"""Orchestrate full legacy database import."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from tenancy.models import Island
from tenancy.services import get_or_create_default_island
from transit.services.legacy_import import MIGRATION_STEPS, run_full_import, run_migration_step


class Command(BaseCommand):
    help = 'Import legacy SaoMiguelBus data into the new tenant-scoped schema'

    def add_arguments(self, parser):
        parser.add_argument(
            '--legacy-db',
            default='sqlite:///../legacy/src/db.sqlite3',
            help='Legacy database URL (sqlite:///path or postgres URL)',
        )
        parser.add_argument(
            '--island',
            default='sao-miguel',
            help='Target island key',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Log steps without writing data',
        )

    def handle(self, *args, **options):
        island_key = options['island']
        legacy_db = options['legacy_db']
        dry_run = options['dry_run']

        island = get_or_create_default_island(island_key)
        self.stdout.write(f'Target island: {island.key} (id={island.id})')

        if dry_run:
            self.stdout.write('Dry run — steps: ' + ', '.join(MIGRATION_STEPS))
            return

        reports = run_full_import(island, legacy_db, dry_run=False)
        for report in reports:
            self.stdout.write(
                f"{report.step}: created={report.created} updated={report.updated} "
                f"errors={len(report.errors)}"
            )
            for error in report.errors[:5]:
                self.stderr.write(f'  {error}')
