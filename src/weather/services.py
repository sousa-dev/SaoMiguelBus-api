"""Parish weather via Open-Meteo (Redis-cached proxy)."""

from __future__ import annotations

import logging
from typing import Any

from django.core.cache import cache

from tenancy.models import Island
from weather.models import Parish
from weather.open_meteo_client import Coord, OpenMeteoError, fetch_forecast

logger = logging.getLogger(__name__)

CACHE_TTL = 3600
ATTRIBUTION = 'Weather data by Open-Meteo.com (CC BY 4.0)'


def _cache_key(island_key: str, slug: str) -> str:
    return f'weather:parish:{island_key}:{slug}'


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
