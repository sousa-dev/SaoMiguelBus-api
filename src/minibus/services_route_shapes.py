"""Harvest and persist PDL Mini Bus route polylines from Eleven Systems AVL."""

from __future__ import annotations

import logging
import re
from typing import Any

from django.db.models import QuerySet
from django.utils import timezone

from minibus.models import MinibusLine
from shared.geo import (  # noqa: F401  (re-exported for existing callers)
    decode_polyline,
    is_plausible_route_coordinates,
)
from minibus.tracking_client import (
    MinibusTrackingError,
    fetch_fleet_locations,
    fetch_vehicle_location,
)
from tenancy.models import Island

logger = logging.getLogger(__name__)

UPSTREAM_AVL_LINE_BY_COLOR: dict[str, str] = {
    'f6bc1c': 'A',
    '00964c': 'B',
    '2d3276': 'C',
    'ec6e00': 'D',
}

DEFAULT_DIRECTION = 0


def minibus_enabled(island: Island) -> bool:
    flags = island.feature_flags or {}
    return bool(flags.get('minibus'))


def normalize_hex_color(value: str | None) -> str | None:
    if not value:
        return None
    stripped = value.strip().lstrip('#').lower()
    if not re.fullmatch(r'[0-9a-f]{6}', stripped):
        return None
    return stripped


def normalize_route_code(route: Any) -> str | None:
    if route is None:
        return None
    if isinstance(route, dict):
        name_short = str(route.get('nameShort') or '').strip()
        if not name_short:
            return None
        if re.fullmatch(r'[A-D]', name_short, re.IGNORECASE):
            return name_short.upper()
        first_char = name_short[0]
        if re.fullmatch(r'[A-D]', first_char, re.IGNORECASE):
            return first_char.upper()
        return None
    route_code = str(route).strip()
    if not route_code or not re.fullmatch(r'[A-D]', route_code, re.IGNORECASE):
        return None
    return route_code.upper()


def vehicle_upstream_color(vehicle: dict[str, Any]) -> str | None:
    color = vehicle.get('color')
    if color:
        return str(color)
    route = vehicle.get('route')
    if isinstance(route, dict) and route.get('color'):
        return str(route['color'])
    return None


def resolve_line_code_from_vehicle(vehicle: dict[str, Any]) -> str | None:
    normalized = normalize_hex_color(vehicle_upstream_color(vehicle))
    if normalized:
        mapped = UPSTREAM_AVL_LINE_BY_COLOR.get(normalized)
        if mapped:
            return mapped

    route_code = normalize_route_code(vehicle.get('route'))
    if route_code:
        return route_code

    return None


def line_has_shape(line: MinibusLine, *, direction: int = DEFAULT_DIRECTION) -> bool:
    for entry in line.route_shapes or []:
        if entry.get('direction') != direction:
            continue
        encoded = str(entry.get('encoded_polyline') or '').strip()
        if encoded and is_plausible_route_coordinates(decode_polyline(encoded)):
            return True
    return False


def lines_missing_shapes(island: Island) -> QuerySet[MinibusLine]:
    lines = MinibusLine.objects.filter(island=island, is_active=True).order_by('sort_order', 'code')
    missing_ids = [line.pk for line in lines if not line_has_shape(line)]
    return MinibusLine.objects.filter(pk__in=missing_ids).order_by('sort_order', 'code')


def any_line_missing_shapes(island: Island) -> bool:
    return lines_missing_shapes(island).exists()


def upsert_route_shape(
    line: MinibusLine,
    *,
    direction: int,
    encoded_polyline: str,
    journey_id: str | None,
    source_vehicle_id: str,
    captured_at: str,
    force: bool,
) -> bool:
    shapes = list(line.route_shapes or [])
    existing_index = next(
        (index for index, row in enumerate(shapes) if row.get('direction') == direction),
        None,
    )
    if existing_index is not None and not force:
        return False

    entry = {
        'direction': direction,
        'encoded_polyline': encoded_polyline,
        'journey_id': journey_id,
        'source_vehicle_id': source_vehicle_id,
        'captured_at': captured_at,
    }
    if existing_index is not None:
        shapes[existing_index] = entry
    else:
        shapes.append(entry)

    line.route_shapes = shapes
    line.save(update_fields=['route_shapes'])
    return True


def pick_fleet_vehicle_ids_by_line(fleet: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for vehicle in fleet:
        line_code = resolve_line_code_from_vehicle(vehicle)
        vehicle_id = str(vehicle.get('id') or '').strip()
        if not line_code or not vehicle_id or line_code in mapping:
            continue
        mapping[line_code] = vehicle_id
    return mapping


def harvest_route_shapes(island: Island, *, force: bool = False) -> dict[str, Any]:
    if not minibus_enabled(island):
        return {
            'status': 'skipped',
            'reason': 'minibus_disabled',
            'harvested': [],
            'missing': [],
            'skipped': [],
            'errors': [],
        }

    missing_lines = list(
        MinibusLine.objects.filter(island=island, is_active=True).order_by('sort_order', 'code'),
    )
    if not force:
        missing_lines = [line for line in missing_lines if not line_has_shape(line)]

    if not missing_lines:
        return {
            'status': 'ok',
            'skipped_all': True,
            'harvested': [],
            'missing': [],
            'skipped': [],
            'errors': [],
        }

    missing_by_code = {line.code.upper(): line for line in missing_lines}
    harvested: list[str] = []
    skipped: list[str] = []
    errors: list[dict[str, str]] = []

    try:
        fleet = fetch_fleet_locations()
    except MinibusTrackingError as exc:
        logger.warning('minibus route shape harvest fleet fetch failed island=%s err=%s', island.key, exc)
        return {
            'status': 'error',
            'reason': 'tracking_unavailable',
            'harvested': [],
            'missing': sorted(missing_by_code.keys()),
            'skipped': [],
            'errors': [{'stage': 'fleet', 'message': str(exc)}],
        }

    fleet_by_line = pick_fleet_vehicle_ids_by_line(fleet)
    captured_at = timezone.now().isoformat()

    for line_code, line in missing_by_code.items():
        vehicle_id = fleet_by_line.get(line_code)
        if not vehicle_id:
            continue

        try:
            detail = fetch_vehicle_location(vehicle_id)
        except MinibusTrackingError as exc:
            errors.append({'line': line_code, 'vehicle_id': vehicle_id, 'message': str(exc)})
            continue

        journey = detail.get('journey') or {}
        encoded = str(journey.get('shape') or '').strip()
        if not encoded or not is_plausible_route_coordinates(decode_polyline(encoded)):
            skipped.append(line_code)
            continue

        direction_raw = journey.get('direction', DEFAULT_DIRECTION)
        try:
            direction = int(direction_raw)
        except (TypeError, ValueError):
            direction = DEFAULT_DIRECTION

        saved = upsert_route_shape(
            line,
            direction=direction,
            encoded_polyline=encoded,
            journey_id=str(journey.get('id')) if journey.get('id') is not None else None,
            source_vehicle_id=vehicle_id,
            captured_at=captured_at,
            force=force,
        )
        if saved:
            harvested.append(line_code)
        else:
            skipped.append(line_code)

    still_missing: list[str] = []
    for code, line in missing_by_code.items():
        line.refresh_from_db()
        if not line_has_shape(line):
            still_missing.append(code)
    still_missing.sort()

    return {
        'status': 'ok',
        'harvested': sorted(harvested),
        'missing': still_missing,
        'skipped': sorted(set(skipped)),
        'errors': errors,
    }
