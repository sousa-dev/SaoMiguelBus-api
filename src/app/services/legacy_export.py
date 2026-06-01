"""Portable JSON snapshot of all legacy production data."""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from datetime import date, datetime
from typing import Any

from django.apps import apps
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import models
from django.utils import timezone

from app.models import LegacyExportJob

EXPORT_FORMAT_VERSION = 2
EXPORT_APP_LABELS = ('app', 'subscriptions')


def _serialize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, models.Model):
        return value.pk
    if isinstance(value, dict):
        return {str(k): _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    return value


def _export_model(model: type[models.Model]) -> list[dict[str, Any]]:
    return [
        {key: _serialize(value) for key, value in record.items()}
        for record in model.objects.all().order_by('pk').values()
    ]


def build_legacy_export() -> dict[str, Any]:
    """Serialize every row from ``app`` and ``subscriptions`` models."""
    tables: dict[str, list[dict[str, Any]]] = {}
    for model in apps.get_models():
        if model._meta.app_label not in EXPORT_APP_LABELS:
            continue
        if model._meta.proxy or model._meta.auto_created:
            continue
        tables[model._meta.db_table] = _export_model(model)

    return {
        'format_version': EXPORT_FORMAT_VERSION,
        'exported_at': timezone.now().isoformat(),
        'source': 'saomiguelbus-legacy-api',
        'tables': tables,
    }


def job_to_dict(job: LegacyExportJob) -> dict[str, Any]:
    return {
        'job_id': job.job_id,
        'status': job.status,
        'started_at': job.started_at.isoformat() if job.started_at else None,
        'finished_at': job.finished_at.isoformat() if job.finished_at else None,
        'exported_at': job.exported_at.isoformat() if job.exported_at else None,
        'export_file': job.export_file.name if job.export_file else None,
        'table_counts': job.table_counts,
        'error': job.error or None,
    }


def get_job(job_id: str) -> LegacyExportJob | None:
    return LegacyExportJob.objects.filter(job_id=job_id).first()


def read_job_status(job_id: str) -> dict[str, Any] | None:
    job = get_job(job_id)
    return job_to_dict(job) if job else None


def write_job_status(job_id: str, **fields: Any) -> dict[str, Any]:
    job = get_job(job_id)
    if job is None:
        raise ValueError(f'Unknown export job: {job_id}')
    for key, value in fields.items():
        setattr(job, key, value)
    job.save()
    return job_to_dict(job)


def read_latest_status() -> dict[str, Any] | None:
    job = LegacyExportJob.objects.order_by('-started_at').first()
    return job_to_dict(job) if job else None


def find_running_job() -> dict[str, Any] | None:
    job = (
        LegacyExportJob.objects.filter(status=LegacyExportJob.STATUS_RUNNING)
        .order_by('-started_at')
        .first()
    )
    return job_to_dict(job) if job else None


def write_legacy_export(job_id: str) -> dict[str, Any]:
    """Build export payload and attach it to the job record."""
    job = get_job(job_id)
    if job is None:
        raise ValueError(f'Unknown export job: {job_id}')

    payload = build_legacy_export()
    body = json.dumps(payload, indent=2, ensure_ascii=False)
    filename = f'smb_legacy_export_{job.job_id}.json'
    job.export_file.save(filename, ContentFile(body.encode('utf-8')), save=False)

    exported_at = timezone.now()
    table_counts = {name: len(rows) for name, rows in payload['tables'].items()}
    job.exported_at = exported_at
    job.table_counts = table_counts
    job.save()

    return {
        'export_path': job.export_file.path if job.export_file else '',
        'table_counts': table_counts,
        'exported_at': exported_at.isoformat(),
    }


def spawn_export_job(job_id: str) -> None:
    import os

    manage_py = os.path.join(settings.BASE_DIR, 'manage.py')
    subprocess.Popen(
        [sys.executable, manage_py, 'export_legacy', '--job-id', job_id],
        cwd=settings.BASE_DIR,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def start_legacy_export_job() -> dict[str, Any]:
    """Create a background export job or return an already running one."""
    running = find_running_job()
    if running:
        return running

    job_id = uuid.uuid4().hex
    job = LegacyExportJob.objects.create(
        job_id=job_id,
        status=LegacyExportJob.STATUS_PENDING,
    )
    spawn_export_job(job_id)
    job.status = LegacyExportJob.STATUS_RUNNING
    job.save(update_fields=['status'])
    return job_to_dict(job)
