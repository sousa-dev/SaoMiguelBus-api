"""Open-Meteo forecast HTTP client (batched multi-location)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import requests
from decouple import config

logger = logging.getLogger(__name__)

OPEN_METEO_BASE_URL = config('OPEN_METEO_BASE_URL', default='https://api.open-meteo.com/v1').rstrip('/')
OPEN_METEO_TIMEOUT = config('OPEN_METEO_TIMEOUT', default=25, cast=int)

CURRENT_VARS = (
    'temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m,precipitation'
)
DAILY_VARS = (
    'weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max'
)
HOURLY_VARS = (
    'temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m,'
    'precipitation,precipitation_probability'
)


class OpenMeteoError(Exception):
    """Open-Meteo API failure."""


@dataclass(frozen=True)
class Coord:
    latitude: float
    longitude: float


def fetch_forecast(coords: list[Coord]) -> list[dict[str, Any]]:
    """Fetch current + daily forecast for one or many coordinates in a single request."""
    if not coords:
        return []

    params = {
        'latitude': ','.join(str(c.latitude) for c in coords),
        'longitude': ','.join(str(c.longitude) for c in coords),
        'current': CURRENT_VARS,
        'daily': DAILY_VARS,
        'timezone': 'auto',
        'forecast_days': '3',
    }
    url = f'{OPEN_METEO_BASE_URL}/forecast'

    try:
        response = requests.get(url, params=params, timeout=OPEN_METEO_TIMEOUT)
    except requests.RequestException as exc:
        logger.exception('Open-Meteo request failed')
        raise OpenMeteoError(str(exc)) from exc

    if not response.ok:
        logger.warning('Open-Meteo HTTP %s: %s', response.status_code, response.text[:500])
        raise OpenMeteoError(f'Open-Meteo HTTP {response.status_code}')

    try:
        payload = response.json()
    except ValueError as exc:
        raise OpenMeteoError('Invalid JSON from Open-Meteo') from exc

    if len(coords) == 1:
        return [payload]
    if isinstance(payload, list):
        if len(payload) != len(coords):
            raise OpenMeteoError(
                f'Open-Meteo returned {len(payload)} results for {len(coords)} coordinates',
            )
        return payload
    raise OpenMeteoError('Unexpected Open-Meteo multi-location response shape')


def fetch_hourly(coord: Coord, *, forecast_days: int) -> dict[str, Any]:
    """Fetch hourly forecast for a single coordinate."""
    if forecast_days < 1 or forecast_days > 3:
        raise ValueError('forecast_days must be between 1 and 3')

    params = {
        'latitude': str(coord.latitude),
        'longitude': str(coord.longitude),
        'hourly': HOURLY_VARS,
        'timezone': 'auto',
        'forecast_days': str(forecast_days),
    }
    url = f'{OPEN_METEO_BASE_URL}/forecast'

    try:
        response = requests.get(url, params=params, timeout=OPEN_METEO_TIMEOUT)
    except requests.RequestException as exc:
        logger.exception('Open-Meteo hourly request failed')
        raise OpenMeteoError(str(exc)) from exc

    if not response.ok:
        logger.warning('Open-Meteo hourly HTTP %s: %s', response.status_code, response.text[:500])
        raise OpenMeteoError(f'Open-Meteo HTTP {response.status_code}')

    try:
        payload = response.json()
    except ValueError as exc:
        raise OpenMeteoError('Invalid JSON from Open-Meteo') from exc

    hourly = payload.get('hourly')
    if not hourly or not hourly.get('time'):
        raise OpenMeteoError('Missing hourly data from Open-Meteo')

    return payload
