"""Azores archipelago island centers for nearest-island seismic labeling."""

from __future__ import annotations

import math
from typing import Any, TypedDict

EARTH_RADIUS_KM = 6371.0

COMPASS_BEARINGS = ('N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW')


class IslandCenter(TypedDict):
    key: str
    name: str
    lat: float
    lng: float


AZORES_ISLANDS: tuple[IslandCenter, ...] = (
    {'key': 'sao-miguel', 'name': 'São Miguel', 'lat': 37.78, 'lng': -25.50},
    {'key': 'santa-maria', 'name': 'Santa Maria', 'lat': 36.97, 'lng': -25.10},
    {'key': 'terceira', 'name': 'Terceira', 'lat': 38.72, 'lng': -27.22},
    {'key': 'graciosa', 'name': 'Graciosa', 'lat': 39.05, 'lng': -28.00},
    {'key': 'sao-jorge', 'name': 'São Jorge', 'lat': 38.65, 'lng': -28.10},
    {'key': 'pico', 'name': 'Pico', 'lat': 38.47, 'lng': -28.40},
    {'key': 'faial', 'name': 'Faial', 'lat': 38.58, 'lng': -28.70},
    {'key': 'flores', 'name': 'Flores', 'lat': 39.45, 'lng': -31.20},
    {'key': 'corvo', 'name': 'Corvo', 'lat': 39.70, 'lng': -31.11},
)


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def bearing(from_lat: float, from_lng: float, to_lat: float, to_lng: float) -> str:
    """Compass direction from (from_lat, from_lng) toward (to_lat, to_lng)."""
    phi1 = math.radians(from_lat)
    phi2 = math.radians(to_lat)
    dlambda = math.radians(to_lng - from_lng)
    y = math.sin(dlambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    degrees = (math.degrees(math.atan2(y, x)) + 360) % 360
    idx = int((degrees + 22.5) / 45) % 8
    return COMPASS_BEARINGS[idx]


def nearest_island(lat: float, lng: float) -> dict[str, Any] | None:
    """Return closest Azores island center and distance in km."""
    if not AZORES_ISLANDS:
        return None

    best: IslandCenter | None = None
    best_dist = float('inf')
    for island in AZORES_ISLANDS:
        dist = _haversine_km(island['lat'], island['lng'], lat, lng)
        if dist < best_dist:
            best_dist = dist
            best = island

    if best is None:
        return None

    return {
        'key': best['key'],
        'name': best['name'],
        'distance_km': round(best_dist, 1),
        'bearing': bearing(best['lat'], best['lng'], lat, lng),
    }


def compute_nearest_fields(latitude: float, longitude: float) -> dict[str, Any]:
    """Model defaults for nearest-island columns."""
    nearest = nearest_island(latitude, longitude)
    if nearest is None:
        return {
            'nearest_island_key': None,
            'nearest_island_name': None,
            'nearest_island_distance_km': None,
            'nearest_island_bearing': None,
        }
    return {
        'nearest_island_key': nearest['key'],
        'nearest_island_name': nearest['name'],
        'nearest_island_distance_km': nearest['distance_km'],
        'nearest_island_bearing': nearest['bearing'],
    }
