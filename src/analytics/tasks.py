"""Analytics retention Celery tasks."""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_MONTHS = 14
IDENTIFYING_PROPERTY_KEYS = frozenset(
    {
        'origin',
        'destination',
        'session_id',
        'user_id',
        'email',
        'device_id',
    }
)


def retention_months_for_island(island) -> int:
    flags = island.feature_flags or {}
    raw = flags.get('analyticsRetentionMonths', DEFAULT_RETENTION_MONTHS)
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_RETENTION_MONTHS


def _strip_identifying_properties(properties: dict) -> dict:
    if not properties:
        return {}
    return {key: value for key, value in properties.items() if key not in IDENTIFYING_PROPERTY_KEYS}


@shared_task(name='analytics.anonymize_events')
def anonymize_analytics_events_task(island_key: str | None = None) -> dict:
    """Drop session_hash and identifying properties from events past retention."""
    from analytics.models import AnalyticsEvent
    from tenancy.models import Island

    islands = Island.objects.all()
    if island_key:
        islands = islands.filter(key=island_key)

    total_anonymized = 0
    for island in islands:
        months = retention_months_for_island(island)
        cutoff = timezone.now() - timedelta(days=months * 30)
        pending = AnalyticsEvent.objects.filter(
            island=island,
            occurred_at__lt=cutoff,
        ).exclude(session_hash='')

        while True:
            batch_ids = list(pending.values_list('id', flat=True)[:500])
            if not batch_ids:
                break
            for event in AnalyticsEvent.objects.filter(id__in=batch_ids):
                event.session_hash = ''
                event.properties = _strip_identifying_properties(event.properties or {})
                event.save(update_fields=['session_hash', 'properties'])
                total_anonymized += 1

    logger.info('Anonymized %s analytics events', total_anonymized)
    return {'status': 'ok', 'anonymized': total_anonymized}
