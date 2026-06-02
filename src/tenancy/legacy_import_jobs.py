"""Legacy import job lifecycle (DB-backed, Celery-driven)."""

from __future__ import annotations

import logging
import traceback
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone

from tenancy.models import LegacyImportJob
from tenancy.services import get_or_create_default_island
from transit.services.legacy_import import (
    FULL_IMPORT_ORDER,
    MigrationReport,
    open_legacy_source,
    resolve_import_steps,
    run_full_import,
    summarize_export_source,
)

logger = logging.getLogger(__name__)


def _resolve_export_path(export_file_path: str) -> Path:
    raw = Path(export_file_path)
    if raw.is_file() or raw.is_dir():
        return raw.resolve()
    media_root = Path(settings.MEDIA_ROOT)
    candidate = media_root / export_file_path
    if candidate.is_file() or candidate.is_dir():
        return candidate.resolve()
    raise FileNotFoundError(
        f'Export path not found: {export_file_path!r} '
        f'(also tried {candidate})'
    )


def create_import_job(
    *,
    island_key: str = 'sao-miguel',
    export_file_path: str = '',
    legacy_db_url: str = '',
    skip_steps: list[str] | None = None,
    essential_only: bool = False,
) -> LegacyImportJob:
    if not export_file_path and not legacy_db_url:
        raise ValueError('Provide export_file_path or legacy_db_url')

    resolved_path = ''
    if export_file_path:
        resolved_path = str(_resolve_export_path(export_file_path))

    steps = resolve_import_steps(skip_steps=skip_steps, essential_only=essential_only)
    job = LegacyImportJob.objects.create(
        job_id=LegacyImportJob.new_job_id(),
        status=LegacyImportJob.STATUS_PENDING,
        island_key=island_key,
        export_file_path=resolved_path,
        legacy_db_url=legacy_db_url or '',
        skip_steps=[step for step in FULL_IMPORT_ORDER if step not in steps],
    )
    return job


def execute_import_job(job_id: str) -> LegacyImportJob:
    job = LegacyImportJob.objects.get(job_id=job_id)
    if job.status == LegacyImportJob.STATUS_COMPLETED:
        logger.info('Import job %s already completed', job_id)
        return job
    if job.status == LegacyImportJob.STATUS_CANCELLED:
        logger.info('Import job %s was cancelled — skipping', job_id)
        return job

    job.status = LegacyImportJob.STATUS_RUNNING
    job.error = ''
    job.started_at = timezone.now()
    job.finished_at = None
    job.save(update_fields=['status', 'error', 'started_at', 'finished_at'])

    try:
        island = get_or_create_default_island(job.island_key)
        legacy = open_legacy_source(
            legacy_db_url=job.legacy_db_url or None,
            export_file=job.export_file_path or None,
        )
        summary = summarize_export_source(legacy)
        job.table_counts = summary.get('table_counts')
        job.save(update_fields=['table_counts'])

        steps = resolve_import_steps(skip_steps=job.skip_steps)
        reports: list[MigrationReport] = []

        def on_step_start(step: str) -> None:
            job.current_step = step
            job.save(update_fields=['current_step'])

        def on_step_complete(report: MigrationReport) -> None:
            reports.append(report)
            job.step_reports = [item.to_dict() for item in reports]
            job.save(update_fields=['step_reports'])

        run_full_import(
            island,
            legacy=legacy,
            steps=steps,
            on_step_start=on_step_start,
            on_step_complete=on_step_complete,
        )

        job.status = LegacyImportJob.STATUS_COMPLETED
        job.current_step = ''
        job.step_reports = [item.to_dict() for item in reports]
        job.finished_at = timezone.now()
        job.save(
            update_fields=['status', 'current_step', 'step_reports', 'finished_at']
        )
        logger.info('Import job %s completed (%d steps)', job_id, len(reports))
        return job
    except Exception as exc:
        job.status = LegacyImportJob.STATUS_FAILED
        job.error = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'error', 'finished_at'])
        logger.exception('Import job %s failed', job_id)
        raise


def enqueue_import_job(job: LegacyImportJob) -> str:
    from tenancy.tasks import run_legacy_import_job

    async_result = run_legacy_import_job.delay(job.job_id)
    job.celery_task_id = async_result.id or ''
    job.save(update_fields=['celery_task_id'])
    return job.celery_task_id


def job_to_dict(job: LegacyImportJob) -> dict[str, Any]:
    return {
        'job_id': job.job_id,
        'status': job.status,
        'island_key': job.island_key,
        'export_file_path': job.export_file_path,
        'legacy_db_url': job.legacy_db_url,
        'skip_steps': job.skip_steps,
        'current_step': job.current_step,
        'step_reports': job.step_reports,
        'table_counts': job.table_counts,
        'celery_task_id': job.celery_task_id,
        'error': job.error,
        'started_at': job.started_at.isoformat() if job.started_at else None,
        'finished_at': job.finished_at.isoformat() if job.finished_at else None,
    }
