"""DSAR export/delete helpers (stub implementation for Phase 2)."""

from __future__ import annotations

from typing import Any

from consent.models import ConsentRecord
from consent.services import hash_session_id, serialize_consent


def resolve_session_hash(*, session_id: str | None, session_hash: str | None, island_key: str) -> str:
    if session_hash:
        return session_hash.strip()
    if session_id:
        return hash_session_id(session_id.strip(), island_key)
    return ''


def dsar_export_bundle(*, session_hash: str) -> dict[str, Any]:
    if not session_hash:
        return {'error': 'session_hash or session_id required'}

    consent_rows = list(
        ConsentRecord.objects.filter(session_hash=session_hash).order_by('-granted_at')[:50]
    )

    analytics_rows = []
    try:
        from analytics.models import AnalyticsEvent

        analytics_rows = list(
            AnalyticsEvent.objects.filter(session_hash=session_hash)
            .order_by('-occurred_at')
            .values('module', 'event_type', 'properties', 'occurred_at', 'platform')[:500]
        )
    except Exception:
        analytics_rows = []

    return {
        'session_hash': session_hash,
        'consent': [serialize_consent(row) for row in consent_rows],
        'analytics_events': analytics_rows,
        'note': 'Stub export — extend with favorites, UGC, and billing when those modules ship.',
    }


def dsar_delete(*, session_hash: str) -> dict[str, Any]:
    if not session_hash:
        return {'error': 'session_hash or session_id required'}

    consent_deleted, _ = ConsentRecord.objects.filter(session_hash=session_hash).delete()

    analytics_anonymized = 0
    try:
        from analytics.models import AnalyticsEvent

        analytics_anonymized = AnalyticsEvent.objects.filter(session_hash=session_hash).update(
            session_hash='',
            properties={},
        )
    except Exception:
        pass

    return {
        'session_hash': session_hash,
        'consent_records_deleted': consent_deleted,
        'analytics_events_anonymized': analytics_anonymized,
        'note': 'Stub delete — extend with cross-module erasure when UGC modules ship.',
    }
