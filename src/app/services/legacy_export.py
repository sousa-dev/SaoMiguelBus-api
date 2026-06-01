"""Portable JSON snapshot of all legacy production data."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from django.apps import apps
from django.db import models
from django.utils import timezone

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
