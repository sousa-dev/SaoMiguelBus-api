"""Sync official Azores trails from trails.visitazores.com (Visit Azores).

azores-hub.net/trails uses the same upstream: it scrapes Visit Azores, caches
list/detail at /api/trails/*, and downloads GPX/KML from trails.visitazores.com.
We read the listing + detail pages directly and extract embedded GeoJSON.
"""

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
from trails.models import Trail
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

# Island.key -> azores-hub feed islandId (optional metadata merge)
AZORES_HUB_ISLAND_IDS: dict[str, str] = {
    'sao-miguel': 'sm',
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


def _trails_feed_base() -> str | None:
    value = (
        getattr(settings, 'TRAILS_FEED_BASE_URL', None)
        or os.environ.get('TRAILS_FEED_BASE_URL')
        or 'https://azores-hub.net/api/trails'
    )
    return str(value).rstrip('/') if value else None


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


def _gpx_url(html: str) -> str:
    match = re.search(r'href="(https?://[^"]+\.gpx)"', html, re.IGNORECASE)
    return match.group(1) if match else ''


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


def _download_geometry(html: str) -> dict[str, Any] | None:
    geometry = _extract_geofield_linestring(html)
    if geometry:
        return geometry

    gpx_link = _gpx_url(html)
    if not gpx_link:
        return None
    response = requests.get(gpx_link, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return gpx_to_linestring(response.text)


def parse_trail_detail_page(html: str, *, page_url: str = '') -> dict[str, Any] | None:
    source_ref = _parse_trail_ref(html)
    if not source_ref:
        logger.warning('visitazores trail missing ref url=%s', page_url)
        return None

    geometry = _download_geometry(html)
    if not geometry:
        logger.warning('visitazores trail missing geometry ref=%s url=%s', source_ref, page_url)
        return None

    fields = _parse_field_items(html)
    name = _parse_trail_name(html) or source_ref

    return {
        'source_ref': source_ref,
        'name': name,
        'difficulty': _parse_difficulty(fields),
        'distance_km': _parse_distance_km(fields),
        'geojson': geometry,
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


def fetch_feed_trail_summaries(island_key: str) -> dict[str, dict[str, Any]]:
    base = _trails_feed_base()
    island_id = AZORES_HUB_ISLAND_IDS.get(island_key)
    if not base or not island_id:
        return {}

    try:
        response = requests.get(f'{base}/list', timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        logger.warning('trails feed list skipped base=%s: %s', base, exc)
        return {}

    trails = payload.get('trails') if isinstance(payload, dict) else None
    if not isinstance(trails, list):
        return {}

    by_ref: dict[str, dict[str, Any]] = {}
    for trail in trails:
        if not isinstance(trail, dict):
            continue
        if trail.get('islandId') != island_id:
            continue
        ref = str(trail.get('ref') or '').upper()
        if ref:
            by_ref[ref] = trail
    return by_ref


def _merge_feed_metadata(row: dict[str, Any], feed: dict[str, Any] | None) -> dict[str, Any]:
    if not feed:
        return row
    if feed.get('namePt') or feed.get('nameEn'):
        row['name'] = str(feed.get('namePt') or feed.get('nameEn'))[:200]
    if feed.get('lengthKm') is not None and row.get('distance_km') is None:
        row['distance_km'] = feed.get('lengthKm')
    if feed.get('difficulty') and not row.get('difficulty'):
        row['difficulty'] = _normalize_difficulty(str(feed['difficulty']))
    return row


def sync_visitazores_trails_for_island(island: Island) -> dict[str, int]:
    counts = {'created': 0, 'updated': 0, 'skipped': 0}
    island_slug = VISITAZORES_ISLAND_SLUGS.get(island.key)
    if not island_slug:
        logger.info('visitazores sync skipped — no slug for island=%s', island.key)
        return counts

    feed_by_ref = fetch_feed_trail_summaries(island.key)
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

            row = _merge_feed_metadata(row, feed_by_ref.get(row['source_ref']))
            _, created = Trail.objects.update_or_create(
                island=island,
                source_ref=row['source_ref'],
                defaults={
                    'name': row['name'],
                    'difficulty': row['difficulty'],
                    'distance_km': row['distance_km'],
                    'geojson': row['geojson'],
                },
            )
            if created:
                counts['created'] += 1
            else:
                counts['updated'] += 1

    return counts
