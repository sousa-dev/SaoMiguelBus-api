"""Portable JSON snapshot of legacy production data for revamp import_legacy."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from django.utils import timezone

from app.models import Ad, Group, Holiday, Info, Route, Stop, Variables
from subscriptions.models import Subscription

EXPORT_FORMAT_VERSION = 1


def _serialize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    return value


def _rows(values_qs) -> list[list[Any]]:
    return [_serialize(list(row)) for row in values_qs]


def build_legacy_export() -> dict[str, Any]:
    """Serialize every table consumed by revamp ``import_legacy``."""
    return {
        'format_version': EXPORT_FORMAT_VERSION,
        'exported_at': timezone.now().isoformat(),
        'source': 'saomiguelbus-legacy-api',
        'tables': {
            'app_variables': _rows(
                Variables.objects.values_list('version', 'maps', 'populate_maps_routes')[:1]
            ),
            'app_stop': _rows(
                Stop.objects.values_list(
                    'id', 'name', 'cleaned_name', 'latitude', 'longitude'
                ).order_by('id')
            ),
            'app_holiday': _rows(
                Holiday.objects.values_list('id', 'date', 'name').order_by('date')
            ),
            'app_group': _rows(
                Group.objects.values_list('id', 'name', 'stops').order_by('id')
            ),
            'app_route': _rows(
                Route.objects.values_list(
                    'id',
                    'route',
                    'stops',
                    'type_of_day',
                    'information',
                    'disabled',
                    'likes',
                    'dislikes',
                ).order_by('id')
            ),
            'app_ad': _rows(
                Ad.objects.values_list(
                    'id',
                    'entity',
                    'description',
                    'media',
                    'start',
                    'end',
                    'action',
                    'target',
                    'advertise_on',
                    'platform',
                    'status',
                    'seen',
                    'clicked',
                ).order_by('id')
            ),
            'app_info': _rows(
                Info.objects.values_list(
                    'id',
                    'titlePT',
                    'messagePT',
                    'titleEN',
                    'messageEN',
                    'titleES',
                    'messageES',
                    'titleFR',
                    'messageFR',
                    'titleDE',
                    'messageDE',
                    'start',
                    'end',
                    'source',
                    'company',
                ).order_by('id')
            ),
            'subscriptions': _rows(
                Subscription.objects.values_list(
                    'id',
                    'email',
                    'is_active',
                    'verification_count',
                    'created_at',
                    'updated_at',
                ).order_by('id')
            ),
        },
    }
