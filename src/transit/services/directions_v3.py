"""v3 directions service — secure proxy without client AUTH_KEY."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from django.conf import settings

from tenancy.models import Island
from transit.models import Stop
from transit.services.schedule_phase import resolve_dataset
from transit.services.directions_cache import (
    build_cache_key,
    get_cached_directions,
    set_cached_directions,
)
from transit.services.legacy_import import clean_string
from transit.services.search import resolve_stop_by_name

logger = logging.getLogger(__name__)

_SERVICE_DAY_MAP = {
    'weekday': (0, 1, 2, 3, 4),
    'saturday': (5,),
    'sunday': (6,),
    'weekday'.upper(): (0, 1, 2, 3, 4),
    'saturday'.upper(): (5,),
    'sunday'.upper(): (6,),
    'WEEKDAY': (0, 1, 2, 3, 4),
    'SATURDAY': (5,),
    'SUNDAY': (6,),
}


def _parse_start_time(start: str) -> tuple[int, int]:
    normalized = start.replace('h', ':').strip()
    if not normalized:
        return 8, 0
    match = re.match(r'^(\d{1,2}):(\d{2})$', normalized)
    if not match:
        return 8, 0
    return int(match.group(1)), int(match.group(2))


def resolve_departure_timestamp(
    *,
    island: Island,
    day: str = '',
    start: str = '',
    date: str = '',
) -> int:
    """Resolve departure time for GMaps from ISO date or service day type."""
    tz = ZoneInfo(island.timezone or 'Atlantic/Azores')
    hour, minute = _parse_start_time(start)

    if date:
        dt = datetime.strptime(date, '%Y-%m-%d')
        dt = dt.replace(hour=hour, minute=minute, second=0, microsecond=0, tzinfo=tz)
        return int(dt.timestamp())

    if day and re.match(r'^\d{4}-\d{2}-\d{2}$', day):
        dt = datetime.strptime(day, '%Y-%m-%d')
        dt = dt.replace(hour=hour, minute=minute, second=0, microsecond=0, tzinfo=tz)
        return int(dt.timestamp())

    now = datetime.now(tz)
    service_key = (day or 'weekday').strip().lower()
    allowed_weekdays = _SERVICE_DAY_MAP.get(service_key) or _SERVICE_DAY_MAP['weekday']

    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate.weekday() in allowed_weekdays and candidate >= now:
        return int(candidate.timestamp())

    for offset in range(1, 8):
        probe = (now + timedelta(days=offset)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        if probe.weekday() in allowed_weekdays:
            return int(probe.timestamp())

    return int(now.timestamp())


def _resolve_stop_query(name: str, dataset: str) -> str:
    """Coordinates if we know the stop, else the raw text for Google to guess.

    Resolves through `resolve_stop_by_name` rather than `name__iexact`: the
    client sends whatever string it has stored, which after canonicalization
    may be a name this stop no longer has. `name__iexact` is also
    accent-sensitive, so "Faja de Baixo" already missed before any rename.
    """
    stop = resolve_stop_by_name(dataset, name)
    if stop:
        return f'{stop.latitude},{stop.longitude}'
    return clean_string(name)


def fetch_gmaps_directions(
    *,
    island: Island,
    origin: str,
    destination: str,
    language_code: str = 'pt',
    arrival_departure: str = 'departure',
    day: str = '',
    start: str = '',
    date: str = '',
) -> tuple[dict, int]:
    """Call Google Directions API (no legacy auth_key gate)."""
    flags = island.feature_flags or {}
    if not flags.get('maps', False):
        return {'error': 'Google Maps API is disabled'}, 400

    if not origin.strip() or not destination.strip():
        return {'error': {'code': 'invalid_params', 'message': 'origin and destination are required'}}, 400

    dataset = resolve_dataset(island)
    origin_query = _resolve_stop_query(origin, dataset)
    dest_query = _resolve_stop_query(destination, dataset)
    transit_time = resolve_departure_timestamp(island=island, day=day, start=start, date=date)

    maps_key = getattr(settings, 'GOOGLE_MAPS_API_KEY', '')
    if not maps_key:
        return {'warning': 'NA'}, 503

    time_param = 'arrival_time' if arrival_departure == 'arrival' else 'departure_time'
    maps_url = (
        f'https://maps.googleapis.com/maps/api/directions/json?'
        f'origin={origin_query}&destination={dest_query}&mode=transit'
        f'&key={maps_key}&language={language_code}&alternatives=true'
        f'&{time_param}={transit_time}'
    )

    try:
        response = requests.get(maps_url, timeout=30)
        if response.status_code != 200:
            return {'warning': 'NA'}, response.status_code
        return response.json(), 200
    except requests.RequestException:
        logger.exception('GMaps proxy failed')
        return {'warning': 'NA'}, 500


def get_directions_v3(
    *,
    island: Island,
    origin: str,
    destination: str,
    language_code: str = 'pt',
    arrival_departure: str = 'departure',
    day: str = '',
    start: str = '',
    date: str = '',
) -> tuple[dict, int, bool]:
    """Return cached or fresh directions. Third tuple element is cache hit."""
    dataset = resolve_dataset(island)
    cache_key = build_cache_key(
        island_key=island.key,
        origin=origin,
        destination=destination,
        day=day or date,
        start=start,
        locale=language_code,
        dataset=dataset,
        arrival_departure=arrival_departure,
    )
    cached = get_cached_directions(cache_key)
    if cached is not None:
        return cached, 200, True

    payload, status_code = fetch_gmaps_directions(
        island=island,
        origin=origin,
        destination=destination,
        language_code=language_code,
        arrival_departure=arrival_departure,
        day=day,
        start=start,
        date=date,
    )
    if status_code == 200 and 'routes' in payload:
        set_cached_directions(cache_key, payload)
    return payload, status_code, False
