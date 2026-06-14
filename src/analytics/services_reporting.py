"""Read-side analytics aggregation for the stats dashboard.

Aggregates both the v3 ``AnalyticsEvent`` stream (consent-gated, tenant scoped)
and the legacy ``Stat`` table (global, compat ingestion) into umami-style
overview payloads plus paginated raw rows.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from django.db.models import Count, Max, Min, Q, QuerySet
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import TruncDay, TruncHour, TruncMonth
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from analytics.models import AnalyticsEvent, Stat
from tenancy.models import Island

DEFAULT_RANGE_DAYS = 30
MAX_PAGE_SIZE = 500
DEFAULT_PAGE_SIZE = 50
BREAKDOWN_LIMIT = 20

# Property-breakdown tuning (v3 event ``properties`` JSON).
PROPERTY_SAMPLE = 5000
PROPERTY_KEY_LIMIT = 16
PROPERTY_VALUE_LIMIT = 20
# Keys excluded from auto-discovery (high-cardinality / not meaningful as a top-N list).
PROPERTY_KEY_DENYLIST = {'lat', 'lng', 'latitude', 'longitude'}

_TRUNCATORS = {
    'hour': TruncHour,
    'day': TruncDay,
    'month': TruncMonth,
}


def parse_range(
    start_raw: str | None,
    end_raw: str | None,
) -> tuple[datetime, datetime]:
    """Resolve a [start, end) window, defaulting to the last 30 days."""
    end = _parse_dt(end_raw, end_of_day=True) or timezone.now()
    start = _parse_dt(start_raw) or (end - timedelta(days=DEFAULT_RANGE_DAYS))
    if start > end:
        start, end = end, start
    return start, end


def resolve_interval(start: datetime, end: datetime, requested: str | None) -> str:
    """Pick a time-series bucket size, honouring an explicit request when valid."""
    if requested in _TRUNCATORS:
        return requested
    span = end - start
    if span <= timedelta(days=2):
        return 'hour'
    if span <= timedelta(days=92):
        return 'day'
    return 'month'


def paginate_params(page_raw: str | None, page_size_raw: str | None) -> tuple[int, int]:
    page = max(_to_int(page_raw, 1), 1)
    page_size = _to_int(page_size_raw, DEFAULT_PAGE_SIZE)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    return page, page_size


# --- v3 AnalyticsEvent -------------------------------------------------------

def v3_overview(
    *,
    island: Island,
    start: datetime,
    end: datetime,
    interval: str,
    module: str | None = None,
    event_type: str | None = None,
    platform: str | None = None,
) -> dict[str, Any]:
    qs = _v3_queryset(island, start, end, module, event_type, platform)

    totals = qs.aggregate(
        events=Count('id'),
        sessions=Count('session_hash', distinct=True, filter=Q(session_hash__gt='')),
    )

    trunc = _TRUNCATORS[interval]
    series_rows = (
        qs.annotate(bucket=trunc('occurred_at'))
        .values('bucket')
        .annotate(
            events=Count('id'),
            sessions=Count('session_hash', distinct=True, filter=Q(session_hash__gt='')),
        )
        .order_by('bucket')
    )
    series = [
        {
            'bucket': _iso(row['bucket']),
            'events': row['events'],
            'sessions': row['sessions'],
        }
        for row in series_rows
    ]

    return {
        'range': {'start': _iso(start), 'end': _iso(end), 'interval': interval},
        'totals': {
            'events': totals['events'] or 0,
            'sessions': totals['sessions'] or 0,
        },
        'series': series,
        'breakdowns': {
            'module': _breakdown(qs, 'module'),
            'event_type': _breakdown(qs, 'event_type'),
            'platform': _breakdown(qs, 'platform'),
            'locale': _breakdown(qs, 'locale'),
        },
    }


def v3_events(
    *,
    island: Island,
    start: datetime,
    end: datetime,
    page: int,
    page_size: int,
    module: str | None = None,
    event_type: str | None = None,
    platform: str | None = None,
) -> dict[str, Any]:
    qs = _v3_queryset(island, start, end, module, event_type, platform)
    count = qs.count()
    offset = (page - 1) * page_size
    rows = qs.order_by('-occurred_at')[offset:offset + page_size]
    results = [
        {
            'id': row.id,
            'module': row.module,
            'event_type': row.event_type,
            'properties': row.properties,
            'platform': row.platform,
            'locale': row.locale,
            'app_version': row.app_version,
            'session_hash': row.session_hash,
            'occurred_at': _iso(row.occurred_at),
        }
        for row in rows
    ]
    return _page_envelope(count, page, page_size, results)


def v3_meta(island: Island) -> dict[str, Any]:
    qs = AnalyticsEvent.objects.for_island(island)
    bounds = qs.aggregate(first=Min('occurred_at'), last=Max('occurred_at'))
    return {
        'modules': _distinct(qs, 'module'),
        'event_types': _distinct(qs, 'event_type'),
        'platforms': _distinct(qs, 'platform'),
        'locales': _distinct(qs, 'locale'),
        'first_event': _iso(bounds['first']),
        'last_event': _iso(bounds['last']),
        'total': qs.count(),
    }


def v3_properties(
    *,
    island: Island,
    start: datetime,
    end: datetime,
    module: str | None = None,
    event_type: str | None = None,
    platform: str | None = None,
    key: str | None = None,
) -> dict[str, Any]:
    """
    Top values for the v3 ``properties`` JSON — the "most searched X" data.

    Without ``key`` it auto-discovers the meaningful property keys in range and
    returns a top-values breakdown for each, plus a combined origin→destination
    routes breakdown. With ``key`` it returns the top values for that one key.
    """
    qs = _v3_queryset(island, start, end, module, event_type, platform)
    base = {'range': {'start': _iso(start), 'end': _iso(end)}, 'total': qs.count()}

    if key:
        return {**base, 'key': key, 'values': _property_values(qs, key)}

    keys = _discover_property_keys(qs)
    breakdowns = {}
    for prop_key in keys:
        values = _property_values(qs, prop_key)
        if values:
            breakdowns[prop_key] = values

    return {
        **base,
        'keys': list(breakdowns.keys()),
        'breakdowns': breakdowns,
        'routes': _v3_route_breakdown(qs),
    }


def _property_values(qs: QuerySet, key: str) -> list[dict[str, Any]]:
    # Blank/empty values are filtered in Python: comparing a KeyTextTransform to
    # '' in SQL trips SQLite's JSON path ("malformed JSON").
    rows = (
        qs.annotate(_pv=KeyTextTransform(key, 'properties'))
        .exclude(_pv__isnull=True)
        .values('_pv')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    out = []
    for row in rows:
        value = row['_pv']
        if value is None or value == '':
            continue
        out.append({'key': value, 'count': row['count']})
        if len(out) >= PROPERTY_VALUE_LIMIT:
            break
    return out


def _v3_route_breakdown(qs: QuerySet) -> list[dict[str, Any]]:
    rows = (
        qs.annotate(
            _o=KeyTextTransform('origin', 'properties'),
            _d=KeyTextTransform('destination', 'properties'),
        )
        .exclude(_o__isnull=True)
        .exclude(_d__isnull=True)
        .values('_o', '_d')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    out = []
    for row in rows:
        origin, destination = row['_o'], row['_d']
        if not origin or not destination:
            continue
        out.append({
            'key': f"{origin} \u2192 {destination}",
            'origin': origin,
            'destination': destination,
            'count': row['count'],
        })
        if len(out) >= PROPERTY_VALUE_LIMIT:
            break
    return out


def _discover_property_keys(qs: QuerySet) -> list[str]:
    """Pick meaningful scalar property keys from a recent sample, by frequency.

    Skips nested values, the float-coordinate denylist, and keys whose sampled
    values are mostly non-integer floats (e.g. raw lat/lng).
    """
    sample = qs.order_by('-occurred_at').values_list('properties', flat=True)[:PROPERTY_SAMPLE]
    freq: dict[str, int] = {}
    floatish: dict[str, int] = {}
    for props in sample:
        if not isinstance(props, dict):
            continue
        for prop_key, value in props.items():
            if prop_key in PROPERTY_KEY_DENYLIST:
                continue
            if value is None or value == '' or isinstance(value, (dict, list)):
                continue
            freq[prop_key] = freq.get(prop_key, 0) + 1
            if isinstance(value, float) and not float(value).is_integer():
                floatish[prop_key] = floatish.get(prop_key, 0) + 1

    keys: list[str] = []
    for prop_key, count in sorted(freq.items(), key=lambda item: -item[1]):
        if floatish.get(prop_key, 0) / count > 0.5:
            continue
        keys.append(prop_key)
    return keys[:PROPERTY_KEY_LIMIT]


# --- legacy Stat -------------------------------------------------------------

def legacy_overview(
    *,
    start: datetime,
    end: datetime,
    interval: str,
    request_type: str | None = None,
    platform: str | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    qs = _legacy_queryset(start, end, request_type, platform, language)

    totals = qs.aggregate(
        stats=Count('id'),
        routes=Count('id', filter=~Q(origin='') & ~Q(destination='')),
    )

    trunc = _TRUNCATORS[interval]
    series_rows = (
        qs.annotate(bucket=trunc('timestamp'))
        .values('bucket')
        .annotate(count=Count('id'))
        .order_by('bucket')
    )
    series = [{'bucket': _iso(row['bucket']), 'count': row['count']} for row in series_rows]

    route_rows = (
        qs.exclude(origin='')
        .exclude(destination='')
        .values('origin', 'destination')
        .annotate(count=Count('id'))
        .order_by('-count')[:BREAKDOWN_LIMIT]
    )
    top_routes = [
        {
            'key': f"{row['origin']} \u2192 {row['destination']}",
            'origin': row['origin'],
            'destination': row['destination'],
            'count': row['count'],
        }
        for row in route_rows
    ]

    return {
        'range': {'start': _iso(start), 'end': _iso(end), 'interval': interval},
        'totals': {
            'stats': totals['stats'] or 0,
            'routes': totals['routes'] or 0,
        },
        'series': series,
        'breakdowns': {
            'request': _breakdown(qs, 'request'),
            'platform': _breakdown(qs, 'platform'),
            'language': _breakdown(qs, 'language'),
            'type_of_day': _breakdown(qs, 'type_of_day'),
            'time': _breakdown(qs.exclude(time='').exclude(time='NA'), 'time'),
            'top_origins': _breakdown(qs.exclude(origin=''), 'origin'),
            'top_destinations': _breakdown(qs.exclude(destination=''), 'destination'),
            'top_routes': top_routes,
        },
    }


def legacy_events(
    *,
    start: datetime,
    end: datetime,
    page: int,
    page_size: int,
    request_type: str | None = None,
    platform: str | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    qs = _legacy_queryset(start, end, request_type, platform, language)
    count = qs.count()
    offset = (page - 1) * page_size
    rows = qs.order_by('-timestamp', '-id')[offset:offset + page_size]
    results = [
        {
            'id': row.id,
            'request': row.request,
            'origin': row.origin,
            'destination': row.destination,
            'type_of_day': row.type_of_day,
            'time': row.time,
            'platform': row.platform,
            'language': row.language,
            'timestamp': _iso(row.timestamp),
        }
        for row in rows
    ]
    return _page_envelope(count, page, page_size, results)


def legacy_meta() -> dict[str, Any]:
    qs = Stat.objects.all()
    bounds = qs.aggregate(first=Min('timestamp'), last=Max('timestamp'))
    return {
        'requests': _distinct(qs, 'request'),
        'platforms': _distinct(qs, 'platform'),
        'languages': _distinct(qs, 'language'),
        'first_event': _iso(bounds['first']),
        'last_event': _iso(bounds['last']),
        'total': qs.count(),
    }


# --- internals ---------------------------------------------------------------

def _v3_queryset(
    island: Island,
    start: datetime,
    end: datetime,
    module: str | None,
    event_type: str | None,
    platform: str | None,
) -> QuerySet:
    qs = AnalyticsEvent.objects.for_island(island).filter(
        occurred_at__gte=start, occurred_at__lte=end
    )
    if module:
        qs = qs.filter(module=module)
    if event_type:
        qs = qs.filter(event_type=event_type)
    if platform:
        qs = qs.filter(platform=platform)
    return qs


def _legacy_queryset(
    start: datetime,
    end: datetime,
    request_type: str | None,
    platform: str | None,
    language: str | None,
) -> QuerySet:
    qs = Stat.objects.filter(timestamp__gte=start, timestamp__lte=end)
    if request_type:
        qs = qs.filter(request=request_type)
    if platform:
        qs = qs.filter(platform=platform)
    if language:
        qs = qs.filter(language=language)
    return qs


def _breakdown(qs: QuerySet, field: str, limit: int = BREAKDOWN_LIMIT) -> list[dict[str, Any]]:
    rows = qs.values(field).annotate(count=Count('id')).order_by('-count')[:limit]
    return [{'key': row[field] or '', 'count': row['count']} for row in rows]


def _distinct(qs: QuerySet, field: str) -> list[str]:
    values = qs.exclude(**{field: ''}).values_list(field, flat=True).distinct().order_by(field)
    return [v for v in values if v]


def _page_envelope(count: int, page: int, page_size: int, results: list) -> dict[str, Any]:
    total_pages = (count + page_size - 1) // page_size if page_size else 0
    return {
        'count': count,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        'results': results,
    }


def _parse_dt(raw: str | None, *, end_of_day: bool = False) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    parsed = parse_datetime(raw)
    if parsed is None:
        day = parse_date(raw)
        if day is None:
            return None
        time_part = (
            datetime.max.time().replace(microsecond=0)
            if end_of_day
            else datetime.min.time()
        )
        parsed = datetime.combine(day, time_part)
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def _to_int(raw: str | None, default: int) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
