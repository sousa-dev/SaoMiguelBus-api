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
            '--export-file',
            help='JSON export from GET /api/v1/export/legacy on production (overrides --legacy-db)',
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
        export_file = options.get('export_file')
        dry_run = options['dry_run']

        island = get_or_create_default_island(island_key)
        self.stdout.write(f'Target island: {island.key} (id={island.id})')
        if export_file:
            self.stdout.write(f'Import source: export file {export_file}')
        else:
            self.stdout.write(f'Import source: legacy database {legacy_db}')

        if dry_run:
            self.stdout.write('Dry run — steps: ' + ', '.join(MIGRATION_STEPS))
            return

        reports = run_full_import(
            island,
            legacy_db_url=legacy_db,
            export_file=export_file,
            dry_run=False,
        )
        for report in reports:
            self.stdout.write(
                f"{report.step}: created={report.created} updated={report.updated} "
                f"errors={len(report.errors)}"
            )
            for error in report.errors[:5]:
                self.stderr.write(f'  {error}')
