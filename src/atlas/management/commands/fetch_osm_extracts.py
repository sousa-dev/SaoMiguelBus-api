"""Populate atlas/data/osm_extract_<island>.json from the live Overpass API.

OsmImporter's own docstring frames extract generation as "Phase 1 tooling infrastructure" —
originally meant to come from a local azores-latest.osm.pbf via osmium/pyrosm. That pipeline
was never built. This command produces the exact same extract shape
(``{"osm_id": ..., "lat": ..., "lon": ..., "tags": {...}}``) from Overpass's public API
instead — same OSM data (ODbL), same downstream importer, no .pbf or native geospatial
dependency required. Network-dependent and explicit — never called from bootstrap_atlas or
any startup path; re-run by hand whenever the extracts need refreshing.

One query per island, built as a union of every ``key=value`` pair in osm_tag_map.json over
that island's bounding box (center_lat/center_lng/radius_km, from tenancy.Island). Queries
nodes and ways (``out center`` gives ways a representative point); relations are skipped —
route=hiking is normally tagged on a relation, not a way, so that category will under-populate
here, which is fine since it's blocklisted for São Miguel (owned by the trails importer) and a
"nice to have" elsewhere, not a correctness requirement.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

import requests
from django.core.management.base import BaseCommand

from atlas.importers.osm import load_tag_map
from tenancy.models import Island

OVERPASS_URL = 'https://overpass-api.de/api/interpreter'
REQUEST_TIMEOUT_S = 180
QUERY_TIMEOUT_S = 120
PAUSE_BETWEEN_ISLANDS_S = 15
MAX_RETRIES = 4
RETRY_BACKOFF_S = 30
# Overpass's own usage guidelines ask for an identifying User-Agent; the default
# `python-requests/…` one is also flatly rejected (406) by its front-end, so this is load-bearing,
# not just courtesy.
REQUEST_HEADERS = {'User-Agent': 'AzoresOfflineMapDataFetch/1.0 (contact: hsousa.2011@gmail.com)'}


def bbox_for(island: Island) -> tuple[float, float, float, float]:
    """(south, west, north, east) — a simple equirectangular box from center + radius, not a
    precise geodesic circle. Generous by design: Overpass only returns nodes/ways that exist,
    so a box padded past the coastline just means a query with mostly-empty ocean, not bad
    data."""
    lat_pad = island.radius_km / 111.0
    lon_pad = island.radius_km / (111.0 * max(math.cos(math.radians(island.center_lat)), 0.1))
    return (
        island.center_lat - lat_pad,
        island.center_lng - lon_pad,
        island.center_lat + lat_pad,
        island.center_lng + lon_pad,
    )


def build_query(bbox: tuple[float, float, float, float], tag_map: dict[str, str]) -> str:
    south, west, north, east = bbox
    bbox_str = f'{south},{west},{north},{east}'
    clauses = []
    for tag_expr in tag_map:
        key, _, value = tag_expr.partition('=')
        clauses.append(f'node["{key}"="{value}"]({bbox_str});')
        clauses.append(f'way["{key}"="{value}"]({bbox_str});')
    body = '\n  '.join(clauses)
    return f'[out:json][timeout:{QUERY_TIMEOUT_S}];\n(\n  {body}\n);\nout center tags;'


def normalize(elements: list[dict]) -> list[dict]:
    """Overpass element → the exact shape OsmImporter.rows() reads."""
    out = []
    for el in elements:
        if el['type'] == 'node':
            lat, lon = el.get('lat'), el.get('lon')
        else:
            center = el.get('center') or {}
            lat, lon = center.get('lat'), center.get('lon')
        if lat is None or lon is None:
            continue
        out.append({'osm_id': f'{el["type"]}/{el["id"]}', 'lat': lat, 'lon': lon, 'tags': el.get('tags') or {}})
    return out


class Command(BaseCommand):
    help = 'Fetch real OSM POI data from Overpass into atlas/data/osm_extract_<island>.json.'

    def add_arguments(self, parser):
        parser.add_argument('--island', help='Only fetch this island key (default: every atlas-enabled island).')

    def handle(self, *args, **options):
        tag_map = load_tag_map()['tag_map']
        data_dir = Path(__file__).resolve().parent.parent.parent / 'data'

        islands = Island.objects.filter(feature_flags__atlas=True).order_by('key')
        if options.get('island'):
            islands = islands.filter(key=options['island'])
            if not islands.exists():
                self.stderr.write(self.style.ERROR(f'No atlas-enabled island with key={options["island"]!r}'))
                return

        for i, island in enumerate(islands):
            if i > 0:
                time.sleep(PAUSE_BETWEEN_ISLANDS_S)

            query = build_query(bbox_for(island), tag_map)
            response = None
            for attempt in range(1, MAX_RETRIES + 1):
                self.stdout.write(f'{island.key}: querying Overpass (attempt {attempt}/{MAX_RETRIES})…')
                try:
                    response = requests.post(
                        OVERPASS_URL, data={'data': query}, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT_S,
                    )
                    response.raise_for_status()
                    break
                except requests.RequestException as exc:
                    response = None
                    # 429 (rate limited) and 504 (the shared instance overloaded) are both
                    # transient — worth a backoff-and-retry. Anything else, give up immediately.
                    status = getattr(exc.response, 'status_code', None)
                    if status not in (429, 504) or attempt == MAX_RETRIES:
                        self.stderr.write(self.style.ERROR(f'{island.key}: Overpass request failed: {exc}'))
                        break
                    wait = RETRY_BACKOFF_S * attempt
                    self.stdout.write(f'{island.key}: {exc} — retrying in {wait}s')
                    time.sleep(wait)

            if response is None:
                continue

            elements = response.json().get('elements', [])
            rows = normalize(elements)
            out_path = data_dir / f'osm_extract_{island.key}.json'
            out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
            self.stdout.write(self.style.SUCCESS(f'{island.key}: wrote {len(rows)} elements → {out_path.name}'))
