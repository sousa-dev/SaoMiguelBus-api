"""Google Maps directions proxy (legacy /api/v1/gmaps)."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from django.conf import settings

from tenancy.models import Island
from transit.models import Stop
from transit.services.schedule_phase import resolve_dataset
from transit.services.legacy_import import clean_string
from transit.services.search import resolve_stop_by_name

logger = logging.getLogger(__name__)


def _is_within_radius(lat: float, lon: float, island: Island) -> bool:
    import math

    def haversine(lat1, lon1, lat2, lon2):
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return haversine(island.center_lat, island.center_lng, lat, lon) <= island.radius_km


def fetch_directions(
    *,
    island: Island,
    origin: str,
    destination: str,
    language_code: str = 'en',
    arrival_departure: str = 'departure',
    day: str = '',
    start: str = '',
    time: str = 'NA',
    version: str = '5',
    auth_key: str = '',
) -> tuple[dict, int]:
    flags = island.feature_flags or {}
    if not flags.get('maps', False):
        return {'error': 'Google Maps API is disabled'}, 400

    expected_key = getattr(settings, 'AUTH_KEY', '')
    if auth_key != expected_key or int(str(version).split('.')[0]) < 5:
        return {'error': 'Unauthorized'}, 401

    dataset = resolve_dataset(island)
    # Via aliases, not `name__iexact`: an old app build sends the stop name it
    # cached, which canonicalization may since have rewritten.
    origin_stop = resolve_stop_by_name(dataset, origin)
    destination_stop = resolve_stop_by_name(dataset, destination)
    origin_query = (
        f'{origin_stop.latitude},{origin_stop.longitude}' if origin_stop else clean_string(origin)
    )
    dest_query = (
        f'{destination_stop.latitude},{destination_stop.longitude}'
        if destination_stop
        else clean_string(destination)
    )

    if day:
        datetime_day = datetime.strptime(day, '%Y-%m-%d')
        if start:
            hour, minute = map(int, start.replace('h', ':').split(':'))
            datetime_day = datetime_day.replace(hour=hour, minute=minute)
        else:
            datetime_day = datetime_day.replace(hour=0, minute=0, second=0, microsecond=0)
        transit_time = int(datetime_day.timestamp())
    elif time != 'NA':
        transit_time = int(time)
    else:
        azores = ZoneInfo(island.timezone or 'Atlantic/Azores')
        transit_time = int(datetime.now(azores).timestamp())

    maps_key = getattr(settings, 'GOOGLE_MAPS_API_KEY', '')
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
        data = response.json()
        return data, 200
    except requests.RequestException as exc:
        logger.exception('GMaps proxy failed: %s', exc)
        return {'warning': 'NA'}, 500
