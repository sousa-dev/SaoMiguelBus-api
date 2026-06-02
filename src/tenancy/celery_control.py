"""Revoke in-flight Celery tasks and purge queued messages."""

from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone

from src.celery import app as celery_app
from tenancy.models import LegacyImportJob

logger = logging.getLogger(__name__)


def _task_id_from_entry(entry: dict[str, Any]) -> str | None:
    request = entry.get('request')
    if isinstance(request, dict):
        task_id = request.get('id')
        if task_id:
            return str(task_id)
    task_id = entry.get('id')
    return str(task_id) if task_id else None


def collect_running_task_ids(*, timeout: float = 3.0) -> list[str]:
    """Return Celery task IDs that are active, reserved, or scheduled."""
    inspect = celery_app.control.inspect(timeout=timeout)
    if inspect is None:
        return []

    task_ids: set[str] = set()
    for method_name in ('active', 'reserved', 'scheduled'):
        grouped = getattr(inspect, method_name)()
        if not grouped:
            continue
        for _worker, entries in grouped.items():
            for entry in entries:
                task_id = _task_id_from_entry(entry)
                if task_id:
                    task_ids.add(task_id)
    return sorted(task_ids)


def revoke_tasks(task_ids: list[str], *, terminate: bool = True) -> int:
    revoked = 0
    for task_id in task_ids:
        celery_app.control.revoke(task_id, terminate=terminate, signal='SIGTERM')
        revoked += 1
    return revoked


def purge_queue() -> int:
    """Drop all pending messages from the default broker queue."""
    return celery_app.control.purge() or 0


def cancel_legacy_import_jobs() -> int:
    """Mark pending/running legacy import jobs as cancelled."""
    now = timezone.now()
    return LegacyImportJob.objects.filter(
        status__in=(LegacyImportJob.STATUS_PENDING, LegacyImportJob.STATUS_RUNNING),
    ).update(
        status=LegacyImportJob.STATUS_CANCELLED,
        error='Cancelled by operator',
        current_step='',
        finished_at=now,
    )


def cancel_all_celery_work(*, terminate_running: bool = True) -> dict[str, Any]:
    """
    Revoke running/reserved/scheduled tasks, purge the queue, and cancel import jobs.

    Safe to call repeatedly. Returns counts for observability.
    """
    task_ids = collect_running_task_ids()
    revoked = revoke_tasks(task_ids, terminate=terminate_running) if task_ids else 0
    purged = purge_queue()
    import_jobs_cancelled = cancel_legacy_import_jobs()

    logger.warning(
        'Celery cancel-all: revoked=%s purged=%s import_jobs_cancelled=%s task_ids=%s',
        revoked,
        purged,
        import_jobs_cancelled,
        task_ids,
    )
    return {
        'revoked': revoked,
        'purged': purged,
        'import_jobs_cancelled': import_jobs_cancelled,
        'task_ids': task_ids,
    }
