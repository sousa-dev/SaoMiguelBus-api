"""Portable JSON snapshot of all legacy production data."""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from django.apps import apps
from django.conf import settings
from django.db import models
from django.utils import timezone

EXPORT_FORMAT_VERSION = 2
EXPORT_APP_LABELS = ('app', 'subscriptions')
EXPORT_DIR_NAME = 'legacy_exports'


def export_root() -> Path:
    root = Path(settings.BASE_DIR) / EXPORT_DIR_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def job_status_path(job_id: str) -> Path:
    return export_root() / f'{job_id}.status.json'


def job_export_path(job_id: str) -> Path:
    return export_root() / f'{job_id}.json'


def latest_status_path() -> Path:
    return export_root() / 'latest.status.json'


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


def write_legacy_export(job_id: str) -> dict[str, Any]:
    """Build export payload and write it to disk for ``job_id``."""
    payload = build_legacy_export()
    export_path = job_export_path(job_id)
    export_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding='utf-8',
    )
    table_counts = {name: len(rows) for name, rows in payload['tables'].items()}
    return {
        'export_path': str(export_path),
        'table_counts': table_counts,
        'exported_at': payload['exported_at'],
    }


def read_job_status(job_id: str) -> dict[str, Any] | None:
    path = job_status_path(job_id)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def write_job_status(job_id: str, **fields: Any) -> dict[str, Any]:
    status = read_job_status(job_id) or {'job_id': job_id}
    status.update(fields)
    payload = json.dumps(status, indent=2)
    job_status_path(job_id).write_text(payload, encoding='utf-8')
    latest_status_path().write_text(payload, encoding='utf-8')
    return status


def read_latest_status() -> dict[str, Any] | None:
    path = latest_status_path()
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def find_running_job() -> dict[str, Any] | None:
    latest = read_latest_status()
    if latest and latest.get('status') == 'running':
        return latest
    return None


def spawn_export_job(job_id: str) -> None:
    manage_py = Path(settings.BASE_DIR) / 'manage.py'
    subprocess.Popen(
        [sys.executable, str(manage_py), 'export_legacy', '--job-id', job_id],
        cwd=str(settings.BASE_DIR),
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
    status = write_job_status(
        job_id,
        status='pending',
        started_at=timezone.now().isoformat(),
        finished_at=None,
        export_file=str(job_export_path(job_id)),
        error=None,
        table_counts=None,
    )
    spawn_export_job(job_id)
    status['status'] = 'running'
    write_job_status(job_id, status='running')
    return read_job_status(job_id) or status
