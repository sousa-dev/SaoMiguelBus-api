"""Sync official Azores trails from trails.visitazores.com (Visit Azores)."""

from __future__ import annotations

import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urljoin

import requests
from django.conf import settings

from tenancy.models import Island
from tenancy.services import for_island
from trails.models import Trail, TrailStage
from trails.services import (
    OPEN_DATA_ATTRIBUTION,
    REQUEST_TIMEOUT_SECONDS,
    _normalize_difficulty,
    feature_in_island,
)

logger = logging.getLogger(__name__)

VISITAZORES_BASE = 'https://trails.visitazores.com'
VISITAZORES_ATTRIBUTION = (
    'Trilhos oficiais — Visit Azores (trails.visitazores.com). '
    + OPEN_DATA_ATTRIBUTION
)

# Island.key -> Visit Azores listing slug (path segment under /en/trails-azores/)
VISITAZORES_ISLAND_SLUGS: dict[str, str] = {
    'sao-miguel': 'sao-miguel',
}

REF_PATTERN = re.compile(
    r'\b((?:PRC|PR|GR)\d+(?:SMI|SMA|PIC|FLW|COR|TER|SJO|GRA))\b',
    re.IGNORECASE,
)
TRAIL_PATH_PATTERN = re.compile(
    r'href="(/en/trails-azores/[^"/]+/[^"]+)"',
    re.IGNORECASE,
)
FIELD_ITEM_PATTERN = re.compile(
    r'field-name-field-([a-z-]+)[^>]*>.*?field-item[^>]*>([^<]+)',
    re.IGNORECASE | re.DOTALL,
)


def _visitazores_base() -> str:
    return (
        getattr(settings, 'VISITAZORES_TRAILS_BASE', None)
        or os.environ.get('VISITAZORES_TRAILS_BASE')
        or VISITAZORES_BASE
    ).rstrip('/')


def _absolute_url(url: str) -> str:
    if not url:
        return ''
    if url.startswith('http://') or url.startswith('https://'):
        return url
    return urljoin(f'{_visitazores_base()}/', url.lstrip('/'))


def _get_html(url: str) -> str:
    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={'User-Agent': 'SaoMiguelBus/1.0 (+https://saomiguelbus.com)'},
    )
    response.raise_for_status()
    return response.text


def _extract_json_object(html: str, needle: str) -> dict[str, Any] | None:
    idx = html.find(needle)
    if idx == -1:
        return None
    start = html.find('{', idx)
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for pos in range(start, len(html)):
        char = html[pos]
        if in_string:
            if escape:
                escape = False
            elif char == '\\':
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                try:
                    payload = json.loads(html[start : pos + 1])
                except json.JSONDecodeError:
                    return None
                return payload if isinstance(payload, dict) else None
    return None


def _extract_geofield_linestring(html: str) -> dict[str, Any] | None:
    geometry = _extract_json_object(html, '"data":{"type":"LineString"')
    if geometry and geometry.get('type') == 'LineString':
        return geometry
    geometry = _extract_json_object(html, '"data":{"type":"MultiLineString"')
    if geometry and geometry.get('type') == 'MultiLineString':
        return geometry
    return None


def _parse_field_items(html: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for match in FIELD_ITEM_PATTERN.finditer(html):
        key = match.group(1).replace('-', '_')
        value = re.sub(r'\s+', ' ', match.group(2)).strip()
        fields[key] = value
    return fields


def _parse_field_href(html: str, field_name: str) -> str:
    match = re.search(
        rf'field-name-field-{field_name}.*?href="([^"]+)"',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return ''
    return _absolute_url(match.group(1))


def _parse_difficulty(fields: dict[str, str]) -> str:
    raw = fields.get('difficulty', '')
    if ' - ' in raw:
        raw = raw.split(' - ', 1)[1]
    return _normalize_difficulty(raw.strip())


def _parse_distance_km(fields: dict[str, str]) -> float | None:
    raw = fields.get('extension', '')
    match = re.search(r'([\d,.]+)\s*km', raw, re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1).replace(',', '.'))
    except ValueError:
        return None


def _parse_shape(fields: dict[str, str]) -> str:
    raw = fields.get('category', '')
    if ' - ' in raw:
        raw = raw.split(' - ', 1)[1]
    value = raw.strip().lower()
    if 'circular' in value:
        return 'circular'
    if 'linear' in value:
        return 'linear'
    return value[:32]


def _parse_duration_min(fields: dict[str, str]) -> int | None:
    raw = fields.get('time_average', '')
    if ' - ' in raw:
        raw = raw.split(' - ', 1)[1]
    raw = raw.strip().lower()
    hours = 0
    minutes = 0
    hour_match = re.search(r'(\d+)\s*h', raw)
    if hour_match:
        hours = int(hour_match.group(1))
    minute_match = re.search(r'(\d+)\s*min', raw)
    if minute_match:
        minutes = int(minute_match.group(1))
    if hours or minutes:
        return hours * 60 + minutes
    return None


def _parse_trail_ref(html: str) -> str:
    for match in REF_PATTERN.finditer(html):
        return match.group(1).upper()
    return ''


def _parse_trail_name(html: str) -> str:
    og = re.search(
        r'<meta\s+property="og:title"\s+content="([^"]+)"',
        html,
        re.IGNORECASE,
    )
    if og:
        title = og.group(1).strip()
        title = re.sub(r'\s*\|\s*Azores Trails\s*$', '', title, flags=re.IGNORECASE)
        if title:
            return title[:200]
    h1 = re.search(r'<h1[^>]*>([^<]+)</h1>', html, re.IGNORECASE)
    if h1:
        return h1.group(1).strip()[:200]
    return ''


def _parse_node_id(html: str) -> int | None:
    for pattern in (r'geofield-map-entity-node-(\d+)', r'/node/(\d+)'):
        match = re.search(pattern, html)
        if match:
            return int(match.group(1))
    return None


def _parse_description(html: str) -> str:
    match = re.search(
        r'field-name-body[^>]*>.*?property="content:encoded"[^>]*>(.*?)</div>',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return ''
    text = re.sub(r'<[^>]+>', ' ', match.group(1))
    return re.sub(r'\s+', ' ', text).strip()


def _gpx_url(html: str) -> str:
    return _parse_field_href(html, 'gpx-file') or (
        (match.group(1) if (match := re.search(r'href="(https?://[^"]+\.gpx)"', html, re.IGNORECASE)) else '')
    )


def _gpx_ns(tag: str) -> str:
    return tag.split('}')[-1] if '}' in tag else tag


def gpx_to_linestring(gpx_text: str) -> dict[str, Any] | None:
    try:
        root = ET.fromstring(gpx_text)
    except ET.ParseError:
        return None

    points: list[list[float]] = []
    for elem in root.iter():
        tag = _gpx_ns(elem.tag)
        if tag == 'trkpt' and elem.get('lat') and elem.get('lon'):
            points.append([float(elem.get('lon')), float(elem.get('lat'))])
        elif tag == 'rtept' and elem.get('lat') and elem.get('lon'):
            points.append([float(elem.get('lon')), float(elem.get('lat'))])

    if len(points) >= 2:
        return {'type': 'LineString', 'coordinates': points}

    waypoints: list[list[float]] = []
    for elem in root.iter():
        if _gpx_ns(elem.tag) == 'wpt' and elem.get('lat') and elem.get('lon'):
            waypoints.append([float(elem.get('lon')), float(elem.get('lat'))])
    if len(waypoints) >= 2:
        return {'type': 'LineString', 'coordinates': waypoints}
    return None


def gpx_to_waypoints(gpx_text: str) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(gpx_text)
    except ET.ParseError:
        return []

    waypoints: list[dict[str, Any]] = []
    for elem in root.iter():
        if _gpx_ns(elem.tag) != 'wpt':
            continue
        lat = elem.get('lat')
        lon = elem.get('lon')
        if not lat or not lon:
            continue
        name = ''
        for child in elem:
            if _gpx_ns(child.tag) == 'name' and child.text:
                name = child.text.strip()
                break
        if not name:
            continue
        waypoints.append(
            {
                'name': name[:200],
                'lat': float(lat),
                'lng': float(lon),
            },
        )
    return waypoints


def gpx_to_stages(gpx_text: str) -> list[dict[str, Any]]:
    """Return stage rows when GPX has multiple named tracks."""
    try:
        root = ET.fromstring(gpx_text)
    except ET.ParseError:
        return []

    stages: list[dict[str, Any]] = []
    for trk in root:
        if _gpx_ns(trk.tag) != 'trk':
            continue
        name = ''
        coordinates: list[list[float]] = []
        for child in trk:
            tag = _gpx_ns(child.tag)
            if tag == 'name' and child.text:
                name = child.text.strip()
            elif tag == 'trkseg':
                for trkpt in child:
                    if _gpx_ns(trkpt.tag) == 'trkpt' and trkpt.get('lat') and trkpt.get('lon'):
                        coordinates.append(
                            [float(trkpt.get('lon')), float(trkpt.get('lat'))],
                        )
        if len(coordinates) >= 2:
            stages.append(
                {
                    'name': (name or f'Stage {len(stages) + 1}')[:200],
                    'geojson': {'type': 'LineString', 'coordinates': coordinates},
                },
            )

    if len(stages) <= 1:
        return []
    return stages


def _start_from_geometry(geometry: dict[str, Any] | None) -> tuple[float | None, float | None]:
    if not geometry:
        return None, None
    coords = geometry.get('coordinates') or []
    geom_type = geometry.get('type')
    if geom_type == 'LineString' and coords:
        return float(coords[0][1]), float(coords[0][0])
    if geom_type == 'MultiLineString' and coords and coords[0]:
        return float(coords[0][0][1]), float(coords[0][0][0])
    return None, None


def _start_from_waypoints(waypoints: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    for waypoint in waypoints:
        sym = str(waypoint.get('name', '')).lower()
        if 'trail head' in sym or waypoint.get('name', '').upper().startswith(('PRC', 'PR', 'GR')):
            return waypoint.get('lat'), waypoint.get('lng')
    if waypoints:
        return waypoints[0].get('lat'), waypoints[0].get('lng')
    return None, None


def _download_gpx_text(html: str) -> str:
    gpx_link = _gpx_url(html)
    if not gpx_link:
        return ''
    response = requests.get(gpx_link, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.text


def _download_geometry(html: str) -> tuple[dict[str, Any] | None, str]:
    geometry = _extract_geofield_linestring(html)
    gpx_text = ''
    try:
        gpx_text = _download_gpx_text(html)
    except Exception as exc:
        logger.warning('visitazores gpx download skipped: %s', exc)

    if not geometry and gpx_text:
        geometry = gpx_to_linestring(gpx_text)
    return geometry, gpx_text


def fetch_pt_translation(node_id: int) -> dict[str, str]:
    url = f'{_visitazores_base()}/pt-pt/node/{node_id}'
    try:
        html = _get_html(url)
    except Exception as exc:
        logger.warning('visitazores PT page skipped node=%s: %s', node_id, exc)
        return {}
    return {'description_pt': _parse_description(html)}


def parse_trail_detail_page(html: str, *, page_url: str = '') -> dict[str, Any] | None:
    source_ref = _parse_trail_ref(html)
    if not source_ref:
        logger.warning('visitazores trail missing ref url=%s', page_url)
        return None

    geometry, gpx_text = _download_geometry(html)
    if not geometry:
        logger.warning('visitazores trail missing geometry ref=%s url=%s', source_ref, page_url)
        return None

    fields = _parse_field_items(html)
    name = _parse_trail_name(html) or source_ref
    waypoints = gpx_to_waypoints(gpx_text) if gpx_text else []
    start_lat, start_lon = _start_from_geometry(geometry)
    if start_lat is None or start_lon is None:
        start_lat, start_lon = _start_from_waypoints(waypoints)

    node_id = _parse_node_id(html)
    description_pt = ''
    if node_id is not None:
        pt = fetch_pt_translation(node_id)
        description_pt = pt.get('description_pt', '')

    return {
        'source_ref': source_ref,
        'name': name,
        'difficulty': _parse_difficulty(fields),
        'distance_km': _parse_distance_km(fields),
        'shape': _parse_shape(fields),
        'duration_min': _parse_duration_min(fields),
        'description_en': _parse_description(html),
        'description_pt': description_pt,
        'gpx_url': _gpx_url(html),
        'kml_url': _parse_field_href(html, 'kml-file'),
        'map_image_url': _parse_field_href(html, 'map-file'),
        'leaflet_url': _parse_field_href(html, 'downloads'),
        'start_lat': start_lat,
        'start_lon': start_lon,
        'waypoints': waypoints,
        'geojson': geometry,
        'stages': gpx_to_stages(gpx_text) if gpx_text else [],
    }


def fetch_island_trail_paths(island_slug: str) -> list[str]:
    listing_url = f'{_visitazores_base()}/en/trails-azores/{island_slug}'
    html = _get_html(listing_url)
    paths: list[str] = []
    seen: set[str] = set()
    for match in TRAIL_PATH_PATTERN.finditer(html):
        path = match.group(1)
        if path.count('/') < 4:
            continue
        if path in seen:
            continue
        seen.add(path)
        paths.append(path)
    return paths


def _sync_trail_stages(trail: Trail, stages: list[dict[str, Any]]) -> None:
    if not stages:
        TrailStage.objects.filter(trail=trail).delete()
        return

    seen_sequences: set[int] = set()
    for index, stage in enumerate(stages, start=1):
        seen_sequences.add(index)
        TrailStage.objects.update_or_create(
            trail=trail,
            sequence=index,
            defaults={
                'island': trail.island,
                'name': stage['name'],
                'geojson': stage['geojson'],
            },
        )
    TrailStage.objects.filter(trail=trail).exclude(sequence__in=seen_sequences).delete()


def sync_visitazores_trails_for_island(island: Island) -> dict[str, int]:
    counts = {'created': 0, 'updated': 0, 'skipped': 0}
    island_slug = VISITAZORES_ISLAND_SLUGS.get(island.key)
    if not island_slug:
        logger.info('visitazores sync skipped — no slug for island=%s', island.key)
        return counts

    paths = fetch_island_trail_paths(island_slug)
    if not paths:
        raise ValueError(f'No trails found on Visit Azores listing for {island_slug}')

    base = _visitazores_base()
    with for_island(island):
        for path in paths:
            page_url = urljoin(f'{base}/', path.lstrip('/'))
            try:
                html = _get_html(page_url)
                row = parse_trail_detail_page(html, page_url=page_url)
            except Exception as exc:
                logger.warning('visitazores trail fetch failed url=%s: %s', page_url, exc)
                counts['skipped'] += 1
                continue

            if not row:
                counts['skipped'] += 1
                continue

            feature = {'type': 'Feature', 'geometry': row['geojson'], 'properties': {}}
            if not feature_in_island(feature, island):
                counts['skipped'] += 1
                continue

            stages = row.pop('stages', [])
            trail, created = Trail.objects.update_or_create(
                island=island,
                source_ref=row['source_ref'],
                defaults={
                    'name': row['name'],
                    'difficulty': row['difficulty'],
                    'distance_km': row['distance_km'],
                    'shape': row['shape'],
                    'duration_min': row['duration_min'],
                    'description_en': row['description_en'],
                    'description_pt': row['description_pt'],
                    'gpx_url': row['gpx_url'],
                    'kml_url': row['kml_url'],
                    'map_image_url': row['map_image_url'],
                    'leaflet_url': row['leaflet_url'],
                    'start_lat': row['start_lat'],
                    'start_lon': row['start_lon'],
                    'waypoints': row['waypoints'],
                    'geojson': row['geojson'],
                },
            )
            _sync_trail_stages(trail, stages)
            if created:
                counts['created'] += 1
            else:
                counts['updated'] += 1

    return counts
