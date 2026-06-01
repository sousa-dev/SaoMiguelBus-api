"""Write legacy export JSON in the background."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from app.services.legacy_export import read_job_status, write_job_status, write_legacy_export


class Command(BaseCommand):
    help = 'Build legacy JSON export file for a background export job'

    def add_arguments(self, parser):
        parser.add_argument('--job-id', required=True, help='Export job identifier')

    def handle(self, *args, **options):
        job_id = options['job_id']
        if read_job_status(job_id) is None:
            raise CommandError(f'Unknown export job: {job_id}')

        write_job_status(job_id, status='running', error=None)
        try:
            result = write_legacy_export(job_id)
        except Exception as exc:
            write_job_status(
                job_id,
                status='failed',
                finished_at=timezone.now().isoformat(),
                error=str(exc),
            )
            raise CommandError(str(exc)) from exc

        write_job_status(
            job_id,
            status='completed',
            finished_at=timezone.now().isoformat(),
            export_file=result['export_path'],
            exported_at=result['exported_at'],
            table_counts=result['table_counts'],
            error=None,
        )
        self.stdout.write(self.style.SUCCESS(f'Export completed: {result["export_path"]}'))
