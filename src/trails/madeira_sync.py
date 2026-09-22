"""Official Madeira hiking routes (Visit Madeira identity + verified OSM geometry).

Route identity, official page and access status come from the Visit Madeira hiking
index; the line geometry comes from the OSM route relation matched to that route by
its official reference. The two are snapshotted offline (see the `data/` files below)
because the app ships them inside an offline bundle — nothing here fetches at runtime.

Two rules this module exists to enforce:

1. **Never invent a track.** A route whose geometry is missing, malformed or outside
   the island's own bounding box is skipped and any trail already stored for it is
   left exactly as it was. A wrong line is worse than no line.
2. **Never imply current access.** Madeira closes and reopens PR routes constantly,
   so the stored description carries the status *as read on the snapshot date* plus
   the official page to check, never a bare "open".

`Trail.leaflet_url` carries the official Visit Madeira route page (the publisher link
the app offers); Madeira publishes no downloadable GPX/KML, so those stay empty and the
offline bundler derives GPX from `Trail.geojson`.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from tenancy.models import Island
from tenancy.services import for_island
from trails.models import Trail
from trails.services import _iter_coordinates, island_bbox

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent / 'data'
OFFICIAL_ROUTES_PATH = DATA_DIR / 'madeira_official_routes.json'
ROUTE_GEOMETRY_PATH = DATA_DIR / 'madeira_route_geometry.json'

MADEIRA_ATTRIBUTION = (
    'Percursos oficiais — Visit Madeira (visitmadeira.com). '
    'Geometria © OpenStreetMap contributors (ODbL). '
    'Confirme sempre o estado do percurso na página oficial antes de caminhar.'
)

# Statuses as published by Visit Madeira on the snapshot date.
STATUS_LABELS_EN = {
    'open': 'open',
    'closed': 'closed',
    'restricted': 'partially closed or restricted',
}
STATUS_LABELS_PT = {
    'open': 'aberto',
    'closed': 'encerrado',
    'restricted': 'parcialmente encerrado ou condicionado',
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        logger.warning('madeira trails source missing: %s', path)
        return {}
    except ValueError:
        logger.exception('madeira trails source is not valid JSON: %s', path)
        return {}


@lru_cache(maxsize=1)
def _load_sources() -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (official route manifest, ref -> geometry). Cached; files are static."""
    return _read_json(OFFICIAL_ROUTES_PATH), _read_json(ROUTE_GEOMETRY_PATH)


def madeira_route_areas() -> set[str]:
    """Island keys the official Visit Madeira hiking index actually publishes routes for.

    Desertas and Selvagens are nature reserves with no public signed trail network, so they
    are absent by fact, not by omission.
    """
    manifest, _ = _load_sources()
    return {str(route.get('island')) for route in manifest.get('routes') or []
            if isinstance(route, dict) and route.get('island')}


def _describe(route: dict[str, Any], accessed: str, lang: str) -> str:
    status = str(route.get('statusAtImport') or '').strip().lower()
    labels = STATUS_LABELS_PT if lang == 'pt' else STATUS_LABELS_EN
    label = labels.get(status, 'unknown' if lang != 'pt' else 'desconhecido')
    url = route.get('officialUrl') or ''
    multi_variant = len(route.get('osmRelationIds') or []) > 1
    start_end = str((route.get('official') or {}).get('startEnd') or '').strip()
    if lang == 'pt':
        text = (
            f'Percurso oficial {route.get("ref", "")} — {route.get("name", "")}. '
            f'Estado em {accessed}: {label}. '
            f'O acesso pode mudar sem aviso; confirme em {url}'
        )
        if start_end:
            text += f' Início/fim: {start_end}.'
        if multi_variant:
            text += (' O mapa mostra as variantes assinaladas deste percurso, '
                     'pelo que a distância total não é indicada.')
        return text.strip()
    text = (
        f'Official route {route.get("ref", "")} — {route.get("name", "")}. '
        f'Status on {accessed}: {label}. '
        f'Access can change without notice; check {url}'
    )
    if start_end:
        text += f' Start/end: {start_end}.'
    if multi_variant:
        text += (' The map shows every signed variant of this route, '
                 'so no single total distance is given.')
    return text.strip()


# Visit Madeira grades every route on this scale; map it onto ours rather than storing the
# publisher's wording, so filters behave the same as on the Azores side.
DIFFICULTY_MAP = {
    'easy': 'easy',
    'moderate': 'moderate',
    'difficult': 'hard',
    'hard': 'hard',
    'very difficult': 'hard',
}


def _official_facts(route: dict[str, Any]) -> dict[str, Any]:
    """Distance, difficulty and duration exactly as Visit Madeira publishes them.

    The matched OSM line is an approximation of the route, not a measurement of it — PR1 is
    published as 6.1 km while its relation measures 5.33 km. Publishing the measured figure
    would present our approximation as the official fact, so a route with no scraped
    distance simply has none.
    """
    official = route.get('official')
    if not isinstance(official, dict):
        return {'distance_km': None, 'difficulty': '', 'duration_min': None}
    distance = official.get('distanceKm')
    duration = official.get('durationMin')
    raw_difficulty = str(official.get('difficulty') or '').strip().lower()
    return {
        'distance_km': float(distance) if isinstance(distance, (int, float)) else None,
        'difficulty': DIFFICULTY_MAP.get(raw_difficulty, ''),
        'duration_min': int(duration) if isinstance(duration, (int, float)) else None,
    }


def _valid_geometry(geometry: Any, island: Island) -> dict[str, Any] | None:
    """Accept only a line geometry whose every vertex falls inside the island bbox."""
    if not isinstance(geometry, dict):
        return None
    if geometry.get('type') not in {'LineString', 'MultiLineString'}:
        return None
    coords = _iter_coordinates(geometry)
    if len(coords) < 2:
        return None
    min_lat, max_lat, min_lng, max_lng = island_bbox(island)
    for lat, lng in coords:
        if not (min_lat <= lat <= max_lat and min_lng <= lng <= max_lng):
            return None
    return geometry


def _start_point(geometry: dict[str, Any]) -> tuple[float | None, float | None]:
    coords = _iter_coordinates(geometry)
    if not coords:
        return None, None
    lat, lng = coords[0]
    return lat, lng


def sync_madeira_trails_for_island(island: Island) -> dict[str, int]:
    """Import the official routes of one Madeira area. Never invents a track.

    Removals are reconciled only against a manifest that actually loaded and actually lists
    this area: a missing or corrupt source file yields no routes, and must empty nothing.
    A route that is still listed but has no usable geometry is kept, not removed — it is a
    published route we currently cannot draw, which is different from a withdrawn one.
    """
    counts = {'created': 0, 'updated': 0, 'skipped': 0, 'removed': 0}
    manifest, geometries = _load_sources()
    routes = manifest.get('routes') or []
    accessed = str(manifest.get('accessed') or 'unknown date')

    listed_refs: set[str] = set()

    with for_island(island):
        for route in routes:
            if not isinstance(route, dict) or route.get('island') != island.key:
                continue
            ref = str(route.get('ref') or '').strip()
            name = str(route.get('name') or '').strip()
            if not ref or not name:
                counts['skipped'] += 1
                continue
            listed_refs.add(ref)
            geometry = _valid_geometry(geometries.get(ref), island)
            if geometry is None:
                # No verified track: leave whatever is already stored untouched.
                logger.info('madeira trail %s skipped: no verified geometry', ref)
                counts['skipped'] += 1
                continue
            start_lat, start_lon = _start_point(geometry)
            _, created = Trail.objects.update_or_create(
                island=island,
                source_ref=ref,
                defaults={
                    'name': name,
                    **_official_facts(route),
                    'geojson': geometry,
                    'description_pt': _describe(route, accessed, 'pt'),
                    'description_en': _describe(route, accessed, 'en'),
                    'leaflet_url': route.get('officialUrl') or '',
                    'start_lat': start_lat,
                    'start_lon': start_lon,
                },
            )
            counts['created' if created else 'updated'] += 1

        if listed_refs:
            withdrawn = Trail.objects.filter(island=island).exclude(source_ref__in=listed_refs)
            removed = withdrawn.count()
            if removed:
                # Atlas picks this up on its next trails import, which tombstones the
                # matching AtlasTrail so clients delete it rather than keeping a route
                # that is no longer published.
                logger.info('madeira trails: removing %s withdrawn route(s) for %s',
                            removed, island.key)
                withdrawn.delete()
            counts['removed'] = removed
    return counts
