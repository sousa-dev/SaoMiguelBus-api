"""Shared geospatial helpers."""

from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lng / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(a))


def is_within_island_radius(
    lat: float,
    lon: float,
    *,
    center_lat: float,
    center_lng: float,
    radius_km: float,
) -> bool:
    """Return True when coordinates are non-zero and within an island bounding radius."""
    if lat == 0.0 and lon == 0.0:
        return False
    return haversine_km(center_lat, center_lng, lat, lon) <= radius_km
