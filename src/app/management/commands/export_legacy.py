"""Write legacy export JSON in the background."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from app.models import LegacyExportJob
from app.services.legacy_export import get_job, write_legacy_export


class Command(BaseCommand):
    help = 'Build legacy JSON export file for a background export job'

    def add_arguments(self, parser):
        parser.add_argument('--job-id', required=True, help='Export job identifier')

    def handle(self, *args, **options):
        job_id = options['job_id']
        job = get_job(job_id)
        if job is None:
            raise CommandError(f'Unknown export job: {job_id}')

        job.status = LegacyExportJob.STATUS_RUNNING
        job.error = ''
        job.save(update_fields=['status', 'error'])

        try:
            result = write_legacy_export(job_id)
        except Exception as exc:
            job.status = LegacyExportJob.STATUS_FAILED
            job.finished_at = timezone.now()
            job.error = str(exc)
            job.save(update_fields=['status', 'finished_at', 'error'])
            raise CommandError(str(exc)) from exc

        exported_at = parse_datetime(result['exported_at']) or timezone.now()
        job.status = LegacyExportJob.STATUS_COMPLETED
        job.finished_at = timezone.now()
        job.exported_at = exported_at
        job.table_counts = result['table_counts']
        job.error = ''
        job.save(
            update_fields=['status', 'finished_at', 'exported_at', 'table_counts', 'error']
        )
        self.stdout.write(self.style.SUCCESS(f'Export completed: {result["export_path"]}'))
