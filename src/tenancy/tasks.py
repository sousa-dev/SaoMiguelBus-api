"""Celery tasks for tenancy / legacy ETL."""

from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings

from tenancy.models import LegacyImportJob
from tenancy.legacy_import_jobs import execute_import_job

logger = logging.getLogger(__name__)

_LEGACY_IMPORT_TIME_LIMIT = getattr(settings, 'LEGACY_IMPORT_TASK_TIME_LIMIT', 6 * 60 * 60)
_LEGACY_IMPORT_SOFT_LIMIT = getattr(settings, 'LEGACY_IMPORT_TASK_SOFT_TIME_LIMIT', 5 * 60 * 60)


@shared_task(
    bind=True,
    name='tenancy.run_legacy_import_job',
    time_limit=_LEGACY_IMPORT_TIME_LIMIT,
    soft_time_limit=_LEGACY_IMPORT_SOFT_LIMIT,
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_legacy_import_job(self, job_id: str) -> dict:
    """Run a LegacyImportJob in the background (no HTTP timeout)."""
    job = LegacyImportJob.objects.filter(job_id=job_id).first()
    if job is None:
        raise ValueError(f'Legacy import job not found: {job_id}')

    if not job.celery_task_id:
        job.celery_task_id = self.request.id or ''
        job.save(update_fields=['celery_task_id'])

    execute_import_job(job_id)
    job.refresh_from_db()
    return {
        'job_id': job.job_id,
        'status': job.status,
        'current_step': job.current_step,
        'step_reports': job.step_reports,
    }
