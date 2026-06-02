"""v3 AnalyticsEvent ingestion."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from analytics.models import AnalyticsEvent
from consent.services import get_latest_consent, normalize_purposes
from tenancy.models import Island


def ingest_events(
    *,
    island: Island,
    events: list[dict[str, Any]],
    session_hash: str,
    consent_session_hash: str,
    platform: str,
    locale: str,
    app_version: str,
) -> tuple[int, int]:
    """
    Store batch of events. Returns (accepted_count, dropped_count).
    Drops row-level storage when analytics consent is not granted.
    """
    consent_record = (
        get_latest_consent(session_hash=consent_session_hash) if consent_session_hash else None
    )
    purposes = normalize_purposes(consent_record.purposes if consent_record else None)
    consent_snapshot = purposes

    if not purposes.get('analytics'):
        return 0, len(events)

    accepted = 0
    for raw in events:
        module = str(raw.get('module', '')).strip()
        event_type = str(raw.get('event_type', '')).strip()
        if not module or not event_type:
            continue

        occurred_at = _parse_occurred_at(raw.get('occurred_at'))
        properties = raw.get('properties') or {}
        if not isinstance(properties, dict):
            properties = {}

        AnalyticsEvent.objects.create(
            island=island,
            module=module,
            event_type=event_type,
            properties=properties,
            session_hash=session_hash if purposes.get('analytics') else '',
            consent_state=consent_snapshot,
            platform=platform or 'web',
            locale=locale or island.default_locale,
            app_version=app_version or '',
            occurred_at=occurred_at,
        )
        accepted += 1

    dropped = len(events) - accepted
    return accepted, dropped


def _parse_occurred_at(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if timezone.is_aware(value) else timezone.make_aware(value)
    if isinstance(value, str):
        parsed = parse_datetime(value)
        if parsed:
            return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)
    return timezone.now()
