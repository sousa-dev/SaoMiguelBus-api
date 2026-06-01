"""Run a single legacy migration step."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from tenancy.services import get_or_create_default_island
from transit.services.legacy_import import MIGRATION_STEPS, run_migration_step


class Command(BaseCommand):
    help = 'Run one idempotent legacy migration step'

    def add_arguments(self, parser):
        parser.add_argument('step', choices=sorted(MIGRATION_STEPS.keys()))
        parser.add_argument(
            '--legacy-db',
            default='sqlite:///../legacy/src/db.sqlite3',
        )
        parser.add_argument(
            '--export-file',
            help='JSON export from GET /api/v1/export/legacy (overrides --legacy-db)',
        )
        parser.add_argument('--island', default='sao-miguel')

    def handle(self, *args, **options):
        step = options['step']
        island = get_or_create_default_island(options['island'])
        try:
            report = run_migration_step(
                step,
                island,
                legacy_db_url=options['legacy_db'],
                export_file=options.get('export_file'),
            )
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f'{step}: created={report.created} updated={report.updated} errors={len(report.errors)}'
            )
        )
        for error in report.errors[:10]:
            self.stderr.write(error)
