"""Cursor-based batched legacy export for large tables (e.g. app_stat)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from django.apps import apps
from django.db import models
from django.utils import timezone

from app.services.legacy_export import EXPORT_APP_LABELS, EXPORT_FORMAT_VERSION, _serialize

DEFAULT_BATCH_LIMIT = 5000
MAX_BATCH_LIMIT = 10000

# Same order as revamp import_legacy (transit first, huge stats mid-export).
EXPORT_TABLE_ORDER = [
    'app_variables',
    'app_stop',
    'app_holiday',
    'app_group',
    'app_route',
    'app_ad',
    'app_info',
    'subscriptions',
    'app_stat',
    'app_data',
    'app_trip',
    'app_tripstop',
    'app_aifeedback',
    'app_emailopen',
]


def exportable_models() -> dict[str, type[models.Model]]:
    models_by_table: dict[str, type[models.Model]] = {}
    for model in apps.get_models():
        if model._meta.app_label not in EXPORT_APP_LABELS:
            continue
        if model._meta.proxy or model._meta.auto_created:
            continue
        models_by_table[model._meta.db_table] = model
    return models_by_table


def parse_cursor(cursor: Optional[str]) -> tuple[str, int]:
    if not cursor:
        return EXPORT_TABLE_ORDER[0], 0
    if ':' not in cursor:
        raise ValueError('Invalid cursor: expected "table_name:last_id"')
    table, raw_id = cursor.split(':', 1)
    if table not in EXPORT_TABLE_ORDER:
        raise ValueError(f'Unknown export table in cursor: {table}')
    try:
        last_id = int(raw_id)
    except ValueError as exc:
        raise ValueError('Invalid cursor: last_id must be an integer') from exc
    if last_id < 0:
        raise ValueError('Invalid cursor: last_id must be >= 0')
    return table, last_id


def _next_table(current: str) -> Optional[str]:
    try:
        index = EXPORT_TABLE_ORDER.index(current)
    except ValueError:
        return None
    if index + 1 >= len(EXPORT_TABLE_ORDER):
        return None
    return EXPORT_TABLE_ORDER[index + 1]


def _serialize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: _serialize(value) for key, value in row.items()} for row in rows]


def batch_export_meta() -> dict[str, Any]:
    return {
        'format_version': EXPORT_FORMAT_VERSION,
        'tables': EXPORT_TABLE_ORDER,
        'default_limit': DEFAULT_BATCH_LIMIT,
        'max_limit': MAX_BATCH_LIMIT,
        'cursor_format': 'table_name:last_id',
    }


def fetch_legacy_batch(*, cursor: Optional[str] = None, limit: int = DEFAULT_BATCH_LIMIT) -> dict[str, Any]:
    """Return the next batch of rows. Cursor format: ``table_name:last_id``."""
    if limit < 1:
        raise ValueError('limit must be >= 1')
    if limit > MAX_BATCH_LIMIT:
        raise ValueError(f'limit must be <= {MAX_BATCH_LIMIT}')

    table, after_id = parse_cursor(cursor)
    models_by_table = exportable_models()

    while True:
        if table not in models_by_table:
            raise ValueError(f'Export table is not available: {table}')

        model = models_by_table[table]
        queryset = model.objects.filter(pk__gt=after_id).order_by('pk')
        raw_rows = list(queryset[:limit].values())
        rows = _serialize_rows(raw_rows)

        if rows:
            last_id = raw_rows[-1]['id']
            table_complete = len(rows) < limit
            if table_complete:
                next_table = _next_table(table)
                if next_table is None:
                    return {
                        'format_version': EXPORT_FORMAT_VERSION,
                        'table': table,
                        'rows': rows,
                        'batch_size': len(rows),
                        'table_complete': True,
                        'export_complete': True,
                        'next': None,
                    }
                return {
                    'format_version': EXPORT_FORMAT_VERSION,
                    'table': table,
                    'rows': rows,
                    'batch_size': len(rows),
                    'table_complete': True,
                    'export_complete': False,
                    'next': f'{next_table}:0',
                }
            return {
                'format_version': EXPORT_FORMAT_VERSION,
                'table': table,
                'rows': rows,
                'batch_size': len(rows),
                'table_complete': False,
                'export_complete': False,
                'next': f'{table}:{last_id}',
            }

        # Empty slice — advance to the next table without extra client round-trips.
        next_table = _next_table(table)
        if next_table is None:
            return {
                'format_version': EXPORT_FORMAT_VERSION,
                'table': table,
                'rows': [],
                'batch_size': 0,
                'table_complete': True,
                'export_complete': True,
                'next': None,
            }
        table = next_table
        after_id = 0
