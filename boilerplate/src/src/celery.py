"""Celery application configuration for djast.

This module initializes the Celery app instance, loads config from Django
settings (prefixed with ``CELERY_``), and auto-discovers tasks from all
installed Django apps.

Usage in production::

    celery -A src worker --loglevel=info
    celery -A src beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
"""

from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.settings")

app = Celery("djast")

app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self: Celery) -> None:
    """Diagnostic task — prints the current request for debugging."""
    print(f"Request: {self.request!r}")
