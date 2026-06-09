"""Parish weather via Open-Meteo (Redis-cached proxy)."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from django.core.cache import cache

from tenancy.models import Island
from weather.models import Parish
from weather.open_meteo_client import Coord, OpenMeteoError, fetch_forecast, fetch_hourly

logger = logging.getLogger(__name__)

CACHE_TTL = 3600
HOURLY_TTL_TODAY = 3600
HOURLY_TTL_FUTURE = 86400
ATTRIBUTION = 'Weather data by Open-Meteo.com (CC BY 4.0)'


def _cache_key(island_key: str, slug: str) -> str:
    return f'weather:parish:{island_key}:{slug}'


def _hourly_cache_key(island_key: str, slug: str, date_str: str) -> str:
    return f'weather:parish:{island_key}:{slug}:hourly:{date_str}'


def _serialize_daily(daily: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not daily:
        return []
    times = daily.get('time') or []
    codes = daily.get('weather_code') or []
    tmax = daily.get('temperature_2m_max') or []
    tmin = daily.get('temperature_2m_min') or []
    precip = daily.get('precipitation_probability_max') or []
    out: list[dict[str, Any]] = []
    for i, day in enumerate(times):
        out.append({
            'date': day,
            'weatherCode': codes[i] if i < len(codes) else None,
            'tempMax': tmax[i] if i < len(tmax) else None,
            'tempMin': tmin[i] if i < len(tmin) else None,
            'precipitationProbabilityMax': precip[i] if i < len(precip) else None,
        })
    return out


def serialize_parish_weather(parish: Parish, raw: dict[str, Any]) -> dict[str, Any]:
    current = raw.get('current') or {}
    return {
        'slug': parish.slug,
        'name': parish.name,
        'concelho': parish.concelho,
        'latitude': parish.latitude,
        'longitude': parish.longitude,
        'current': {
            'temperature': current.get('temperature_2m'),
            'weatherCode': current.get('weather_code'),
            'windSpeed': current.get('wind_speed_10m'),
            'humidity': current.get('relative_humidity_2m'),
            'precipitation': current.get('precipitation'),
            'time': current.get('time'),
        },
        'daily': _serialize_daily(raw.get('daily')),
        'attribution': ATTRIBUTION,
    }


def _store_forecasts(island_key: str, parishes: list[Parish], raws: list[dict[str, Any]]) -> int:
    count = 0
    for parish, raw in zip(parishes, raws, strict=True):
        payload = serialize_parish_weather(parish, raw)
        cache.set(_cache_key(island_key, parish.slug), payload, CACHE_TTL)
        count += 1
    return count


def refresh_parishes(parishes: list[Parish]) -> int:
    """Batch-fetch Open-Meteo for the given parishes and write cache entries."""
    if not parishes:
        return 0
    island_key = parishes[0].island.key
    coords = [Coord(p.latitude, p.longitude) for p in parishes]
    raws = fetch_forecast(coords)
    return _store_forecasts(island_key, parishes, raws)


def refresh_all_parishes(island: Island) -> int:
    parishes = list(
        Parish.objects.filter(island=island, is_active=True).order_by('concelho', 'name'),
    )
    return refresh_parishes(parishes)


def get_cached_parish_weather(island_key: str, slug: str) -> dict[str, Any] | None:
    cached = cache.get(_cache_key(island_key, slug))
    return cached if cached is not None else None


def get_parish_weather(parish: Parish) -> dict[str, Any]:
    island_key = parish.island.key
    cached = get_cached_parish_weather(island_key, parish.slug)
    if cached is not None:
        return cached
    refresh_parishes([parish])
    cached = get_cached_parish_weather(island_key, parish.slug)
    if cached is None:
        raise OpenMeteoError(f'Failed to cache weather for {parish.slug}')
    return cached


def list_parish_weather(island: Island) -> list[dict[str, Any]]:
    parishes = list(
        Parish.objects.filter(island=island, is_active=True).order_by('concelho', 'name'),
    )
    if not parishes:
        return []

    island_key = island.key
    results: list[dict[str, Any]] = []
    missing: list[Parish] = []

    for parish in parishes:
        cached = get_cached_parish_weather(island_key, parish.slug)
        if cached is not None:
            results.append(cached)
        else:
            missing.append(parish)

    if missing:
        try:
            refresh_parishes(missing)
        except OpenMeteoError:
            if not results:
                raise
            logger.warning('Partial weather refresh failed for %s parishes', len(missing))
        for parish in missing:
            cached = get_cached_parish_weather(island_key, parish.slug)
            if cached is not None:
                results.append(cached)

    results.sort(key=lambda row: (row.get('concelho', ''), row.get('name', '')))
    return results


def _allowed_forecast_dates(parish_weather: dict[str, Any]) -> set[str]:
    daily = parish_weather.get('daily') or []
    return {row['date'] for row in daily if row.get('date')}


def _parish_local_today(parish_weather: dict[str, Any]) -> date:
    current_time = (parish_weather.get('current') or {}).get('time')
    if current_time:
        return date.fromisoformat(str(current_time).split('T')[0])
    daily = parish_weather.get('daily') or []
    if daily and daily[0].get('date'):
        return date.fromisoformat(daily[0]['date'])
    return date.today()


def _forecast_days_for_date(local_today: date, target: date) -> int:
    delta = (target - local_today).days
    return min(3, max(1, delta + 1))


def _serialize_hourly_slots(hourly: dict[str, Any], target_date: str) -> list[dict[str, Any]]:
    times = hourly.get('time') or []
    temps = hourly.get('temperature_2m') or []
    codes = hourly.get('weather_code') or []
    winds = hourly.get('wind_speed_10m') or []
    humidities = hourly.get('relative_humidity_2m') or []
    precips = hourly.get('precipitation') or []
    precip_probs = hourly.get('precipitation_probability') or []
    out: list[dict[str, Any]] = []
    for i, time_str in enumerate(times):
        if str(time_str).split('T')[0] != target_date:
            continue
        out.append({
            'time': time_str,
            'temperature': temps[i] if i < len(temps) else None,
            'weatherCode': codes[i] if i < len(codes) else None,
            'windSpeed': winds[i] if i < len(winds) else None,
            'humidity': humidities[i] if i < len(humidities) else None,
            'precipitation': precips[i] if i < len(precips) else None,
            'precipitationProbability': precip_probs[i] if i < len(precip_probs) else None,
        })
    return out


def get_parish_hourly(parish: Parish, date_str: str) -> dict[str, Any]:
    """Return hourly slots for one parish on a date within the 3-day forecast window."""
    try:
        target_date = date.fromisoformat(date_str)
    except ValueError as exc:
        raise ValueError('Invalid date format; use YYYY-MM-DD') from exc

    parish_weather = get_parish_weather(parish)
    allowed = _allowed_forecast_dates(parish_weather)
    if date_str not in allowed:
        raise ValueError(f'Date {date_str} is outside the forecast window')

    island_key = parish.island.key
    cache_key = _hourly_cache_key(island_key, parish.slug, date_str)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    local_today = _parish_local_today(parish_weather)
    forecast_days = _forecast_days_for_date(local_today, target_date)
    raw = fetch_hourly(
        Coord(parish.latitude, parish.longitude),
        forecast_days=forecast_days,
    )
    hourly = raw.get('hourly')
    if not hourly:
        raise OpenMeteoError('Missing hourly data from Open-Meteo')

    hours = _serialize_hourly_slots(hourly, date_str)
    payload = {
        'slug': parish.slug,
        'date': date_str,
        'hours': hours,
        'attribution': ATTRIBUTION,
    }

    ttl = HOURLY_TTL_TODAY if target_date == local_today else HOURLY_TTL_FUTURE
    cache.set(cache_key, payload, ttl)
    return payload
