"""Redis-backed cache for Google Maps directions responses."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from django.core.cache import cache

DIRECTIONS_CACHE_TTL = 60 * 60 * 24  # 24 hours


def build_cache_key(
    *,
    island_key: str,
    origin: str,
    destination: str,
    day: str,
    start: str,
    locale: str,
    dataset: str,
    arrival_departure: str = 'departure',
) -> str:
    raw = '|'.join(
        [
            island_key,
            origin.strip().lower(),
            destination.strip().lower(),
            day.strip().lower(),
            start.strip().lower(),
            locale.strip().lower(),
            # Without this, preview and live share a cached Google result for
            # 24h, and post-cutover the same stop names resolve to the other
            # network's coordinates (98 section 4 gap).
            dataset.strip().lower(),
            arrival_departure.strip().lower(),
        ]
    )
    digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]
    return f'gmaps:directions:{digest}'


def get_cached_directions(cache_key: str) -> dict[str, Any] | None:
    cached = cache.get(cache_key)
    if cached is None:
        return None
    if isinstance(cached, dict):
        return cached
    try:
        return json.loads(cached)
    except (TypeError, json.JSONDecodeError):
        return None


def set_cached_directions(cache_key: str, payload: dict[str, Any]) -> None:
    cache.set(cache_key, payload, timeout=DIRECTIONS_CACHE_TTL)
