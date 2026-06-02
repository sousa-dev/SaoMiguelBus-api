"""Orchestrate full legacy database import."""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from tenancy.models import LegacyImportJob
from tenancy.legacy_import_jobs import (
    create_import_job,
    enqueue_import_job,
    execute_import_job,
)
from tenancy.services import get_or_create_default_island
from transit.services.legacy_import import (
    FULL_IMPORT_ORDER,
    open_legacy_source,
    resolve_import_steps,
    run_full_import,
    summarize_export_source,
)


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
            help='Legacy export JSON file OR batched export directory with manifest.json',
        )
        parser.add_argument(
            '--export-dir',
            help='Batched export directory (manifest.json + JSONL batches). Overrides --export-file.',
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
        parser.add_argument(
            '--async',
            dest='run_async',
            action='store_true',
            help='Queue import on Celery worker (recommended for large export JSON files)',
        )
        parser.add_argument(
            '--job-id',
            help='Run or re-run an existing LegacyImportJob by job_id (used by Celery worker)',
        )
        parser.add_argument(
            '--essential-only',
            action='store_true',
            help='Skip optional archive steps (data, legacy_trips, legacy_tripstops, aifeedback, emailopens)',
        )
        parser.add_argument(
            '--skip-steps',
            help='Comma-separated migration steps to skip (e.g. data,legacy_trips)',
        )

    def handle(self, *args, **options):
        job_id = options.get('job_id')
        if job_id:
            self._run_job(job_id)
            return

        island_key = options['island']
        legacy_db = options['legacy_db']
        export_file = options.get('export_dir') or options.get('export_file')
        dry_run = options['dry_run']
        run_async = options['run_async']
        essential_only = options['essential_only']
        skip_steps_raw = options.get('skip_steps') or ''
        skip_steps = [part.strip() for part in skip_steps_raw.split(',') if part.strip()]

        island = get_or_create_default_island(island_key)
        self.stdout.write(f'Target island: {island.key} (id={island.id})')
        if export_file:
            kind = 'batched directory' if Path(export_file).is_dir() else 'JSON file'
            self.stdout.write(f'Import source: export {kind} {export_file}')
        else:
            self.stdout.write(f'Import source: legacy database {legacy_db}')

        steps = resolve_import_steps(skip_steps=skip_steps, essential_only=essential_only)
        if dry_run:
            self.stdout.write('Dry run — steps: ' + ', '.join(steps))
            return

        if run_async:
            if not export_file and not legacy_db:
                raise CommandError('--export-file or --legacy-db is required with --async')
            job = create_import_job(
                island_key=island_key,
                export_file_path=export_file or '',
                legacy_db_url=legacy_db if not export_file else '',
                skip_steps=skip_steps,
                essential_only=essential_only,
            )
            task_id = enqueue_import_job(job)
            self.stdout.write(self.style.SUCCESS(f'Queued legacy import job {job.job_id}'))
            self.stdout.write(f'  Celery task: {task_id}')
            self.stdout.write(f'  Steps: {", ".join(steps)}')
            self.stdout.write('  Monitor in Django admin → Legacy import jobs')
            return

        legacy = open_legacy_source(
            legacy_db_url=legacy_db if not export_file else None,
            export_file=export_file,
        )
        summary = summarize_export_source(legacy)
        if summary.get('table_counts'):
            self.stdout.write('Export table counts:')
            for name, count in sorted(summary['table_counts'].items()):
                self.stdout.write(f'  {name}: {count}')

        reports = run_full_import(
            island,
            legacy=legacy,
            steps=steps,
        )
        self._print_reports(reports)

    def _run_job(self, job_id: str) -> None:
        job = LegacyImportJob.objects.filter(job_id=job_id).first()
        if job is None:
            raise CommandError(f'Legacy import job not found: {job_id}')
        self.stdout.write(f'Running import job {job_id} (status={job.status})...')
        job = execute_import_job(job_id)
        if job.status == LegacyImportJob.STATUS_FAILED:
            raise CommandError(job.error or f'Import job {job_id} failed')
        self.stdout.write(self.style.SUCCESS(f'Import job {job_id} completed'))
        for item in job.step_reports or []:
            self.stdout.write(
                f"{item['step']}: created={item['created']} updated={item['updated']} "
                f"errors={len(item.get('errors') or [])}"
            )

    def _print_reports(self, reports) -> None:
        for report in reports:
            self.stdout.write(
                f"{report.step}: created={report.created} updated={report.updated} "
                f"errors={len(report.errors)}"
            )
            for error in report.errors[:5]:
                self.stderr.write(f'  {error}')
