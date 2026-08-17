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


# --- Google encoded polylines --- #
#
# Both bus networks speak this format: the minibus AVL harvest stores
# `encoded_polyline` per line, and the AzoresBus schedule importer stores
# `ExternalJourney.shape` per trip. They live here rather than in either app so
# there is ONE decoder -- the app already learned that lesson with pair matching
# (`transit/services/matcher.py`), where three implementations of one rule
# drifted apart and produced bugs nobody could see.

POLYLINE_PRECISION = 1e5


def decode_polyline(encoded: str) -> list[tuple[float, float]]:
    """Google Encoded Polyline Algorithm -> [(lat, lng), ...]."""
    if not encoded:
        return []

    coordinates: list[tuple[float, float]] = []
    index = 0
    lat = 0
    lng = 0
    length = len(encoded)

    while index < length:
        for axis in range(2):
            shift = 0
            result = 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            delta = ~(result >> 1) if (result & 1) else (result >> 1)
            if axis == 0:
                lat += delta
            else:
                lng += delta

        coordinates.append((lat / POLYLINE_PRECISION, lng / POLYLINE_PRECISION))

    return coordinates


def _encode_value(value: int, out: list[str]) -> None:
    value = ~(value << 1) if value < 0 else (value << 1)
    while value >= 0x20:
        out.append(chr((0x20 | (value & 0x1F)) + 63))
        value >>= 5
    out.append(chr(value + 63))


def encode_polyline(coordinates: list[tuple[float, float]]) -> str:
    """The inverse of `decode_polyline`, so a trimmed path can go back on the wire.

    Round-tripping is lossy only to the 1e5 grid (about a metre), which is far
    below the accuracy of the stop positions this is ever compared against.
    """
    out: list[str] = []
    previous_lat = 0
    previous_lng = 0

    for lat, lng in coordinates:
        scaled_lat = round(lat * POLYLINE_PRECISION)
        scaled_lng = round(lng * POLYLINE_PRECISION)
        _encode_value(scaled_lat - previous_lat, out)
        _encode_value(scaled_lng - previous_lng, out)
        previous_lat = scaled_lat
        previous_lng = scaled_lng

    return ''.join(out)


def is_plausible_route_coordinates(coordinates: list[tuple[float, float]]) -> bool:
    """Reject a path that decoded to nothing, or to Null Island."""
    if len(coordinates) < 2:
        return False
    return all(abs(lat) > 1 and abs(lng) > 1 for lat, lng in coordinates)
