"""EMSC FDSN ingest and seismic event queries."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import requests
from django.db.models import Count
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from seismic.models import FeltReport, SeismicEvent
from tenancy.models import Island
from tenancy.services import for_island

logger = logging.getLogger(__name__)

FDSN_EVENT_URL = 'https://www.seismicportal.eu/fdsnws/event/1/query'
DEFAULT_MIN_MAGNITUDE = 2.0
DEFAULT_LOOKBACK_DAYS = 30
# Island.radius_km is transit-local (~50); seismic covers the whole archipelago.
SEISMIC_MIN_RADIUS_KM = 400
KM_PER_DEGREE_LAT = 111.0
REQUEST_TIMEOUT_SECONDS = 30


def _km_to_degrees(km: float) -> float:
    return max(km / KM_PER_DEGREE_LAT, 0.1)


def _parse_occurred_at(raw: str | None) -> Any:
    if not raw:
        return timezone.now()
    parsed = parse_datetime(str(raw).replace('Z', '+00:00'))
    if parsed is None:
        return timezone.now()
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)


def _parse_feature(feature: dict[str, Any]) -> dict[str, Any] | None:
    props = feature.get('properties') or {}
    emsc_id = str(props.get('unid') or feature.get('id') or '').strip()
    if not emsc_id:
        return None

    geometry = feature.get('geometry') or {}
    coordinates = geometry.get('coordinates') or []
    lon = props.get('lon')
    lat = props.get('lat')
    depth = props.get('depth')
    if lon is None and len(coordinates) >= 2:
        lon = coordinates[0]
    if lat is None and len(coordinates) >= 2:
        lat = coordinates[1]
    if depth is None and len(coordinates) >= 3:
        depth = coordinates[2]

    try:
        magnitude = float(props.get('mag'))
        latitude = float(lat)
        longitude = float(lon)
    except (TypeError, ValueError):
        return None

    depth_km = None
    if depth is not None:
        try:
            depth_km = float(depth)
        except (TypeError, ValueError):
            depth_km = None

    region = str(props.get('flynn_region') or props.get('place') or '').strip()[:200]
    occurred_at = _parse_occurred_at(props.get('time'))

    return {
        'emsc_id': emsc_id,
        'magnitude': magnitude,
        'depth_km': depth_km,
        'latitude': latitude,
        'longitude': longitude,
        'occurred_at': occurred_at,
        'region': region,
    }


def build_fdsn_params(island: Island) -> dict[str, str]:
    start = timezone.now() - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    radius_km = max(float(island.radius_km), float(SEISMIC_MIN_RADIUS_KM))
    max_radius_deg = _km_to_degrees(radius_km)
    return {
        'format': 'json',
        'starttime': start.strftime('%Y-%m-%dT%H:%M:%S'),
        'latitude': str(island.center_lat),
        'longitude': str(island.center_lng),
        'maxradius': f'{max_radius_deg:.4f}',
        'minmag': str(DEFAULT_MIN_MAGNITUDE),
        'limit': '500',
        'orderby': 'time',
    }


def fetch_events_for_island(island: Island) -> list[dict[str, Any]]:
    """Fetch parsed event dicts from EMSC for one island."""
    params = build_fdsn_params(island)
    response = requests.get(FDSN_EVENT_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    if response.status_code == 204 or not response.content.strip():
        return []
    payload = response.json()
    features = payload.get('features') or []
    if not isinstance(features, list):
        raise ValueError('EMSC response missing features list')

    parsed: list[dict[str, Any]] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        row = _parse_feature(feature)
        if row:
            parsed.append(row)
    return parsed


def sync_events_for_island(island: Island) -> dict[str, int]:
    """Upsert seismic events for one island. Returns created/updated/skipped counts."""
    counts = {'created': 0, 'updated': 0, 'skipped': 0}
    try:
        rows = fetch_events_for_island(island)
    except Exception:
        logger.exception('seismic sync failed for island=%s', island.key)
        raise

    with for_island(island):
        for row in rows:
            _, created = SeismicEvent.objects.update_or_create(
                island=island,
                emsc_id=row['emsc_id'],
                defaults={
                    'magnitude': row['magnitude'],
                    'depth_km': row['depth_km'],
                    'latitude': row['latitude'],
                    'longitude': row['longitude'],
                    'occurred_at': row['occurred_at'],
                    'region': row['region'],
                },
            )
            if created:
                counts['created'] += 1
            else:
                counts['updated'] += 1
    return counts


def _islands_for_sync(*, island_key: str | None) -> list[Island]:
    if island_key:
        return list(Island.objects.filter(key=island_key))
    return [
        island
        for island in Island.objects.all()
        if (island.feature_flags or {}).get('seismic')
    ]


def sync_all_events(*, island_key: str | None = None) -> dict[str, int]:
    """Sync EMSC events for configured islands."""
    totals = {'islands': 0, 'created': 0, 'updated': 0, 'skipped': 0}
    for island in _islands_for_sync(island_key=island_key):
        totals['islands'] += 1
        counts = sync_events_for_island(island)
        totals['created'] += counts['created']
        totals['updated'] += counts['updated']
        totals['skipped'] += counts['skipped']
    return totals


def _felt_summary(event: SeismicEvent) -> dict[str, int]:
    rows = (
        FeltReport.objects.filter(event=event)
        .values('intensity')
        .annotate(count=Count('id'))
        .order_by('intensity')
    )
    return {str(row['intensity']): row['count'] for row in rows}


def serialize_event(event: SeismicEvent, *, include_felt: bool = True) -> dict[str, Any]:
    payload: dict[str, Any] = {
        'id': event.id,
        'emscId': event.emsc_id,
        'magnitude': event.magnitude,
        'depthKm': event.depth_km,
        'latitude': event.latitude,
        'longitude': event.longitude,
        'occurredAt': event.occurred_at.isoformat(),
        'region': event.region,
    }
    if include_felt:
        payload['feltCount'] = event.felt_reports.count()
        payload['feltSummary'] = _felt_summary(event)
    return payload


def list_events(*, min_magnitude: float | None = None, limit: int = 50) -> list[dict[str, Any]]:
    qs = SeismicEvent.objects.order_by('-occurred_at')
    if min_magnitude is not None:
        qs = qs.filter(magnitude__gte=min_magnitude)
    limit = max(1, min(limit, 100))
    return [serialize_event(event, include_felt=True) for event in qs[:limit]]


def get_event(event_id: int) -> dict[str, Any] | None:
    try:
        event = SeismicEvent.objects.get(id=event_id)
    except SeismicEvent.DoesNotExist:
        return None
    return serialize_event(event, include_felt=True)


def submit_felt_report(
    *,
    event_id: int,
    session_hash: str,
    intensity: int,
    latitude: float | None = None,
    longitude: float | None = None,
) -> tuple[dict[str, Any], bool]:
    """Upsert felt report. Returns (payload, created)."""
    event = SeismicEvent.objects.get(id=event_id)
    defaults: dict[str, Any] = {'intensity': intensity}
    if latitude is not None:
        defaults['latitude'] = round(latitude, 2)
    if longitude is not None:
        defaults['longitude'] = round(longitude, 2)

    defaults['island'] = event.island
    report, created = FeltReport.objects.update_or_create(
        event=event,
        session_hash=session_hash,
        defaults=defaults,
    )
    return {
        'eventId': event.id,
        'intensity': report.intensity,
        'feltCount': event.felt_reports.count(),
        'feltSummary': _felt_summary(event),
    }, created
