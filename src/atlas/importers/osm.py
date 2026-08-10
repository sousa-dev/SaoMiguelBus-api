"""Utility POI layer extracted from the local OSM .pbf (SDD 07 §5, 02 §5.2).

This importer's input is a pre-extracted, normalised JSON file — a flat list of
``{"osm_id": ..., "lat": ..., "lon": ..., "tags": {...}}`` — not the raw .pbf. Turning
``azores-latest.osm.pbf`` into that file (osmium/pyrosm export, or an Overpass-shaped dump of
the same local file) is Phase 1 tooling infrastructure, not this app's job; it's what keeps
this importer's actual logic (tag mapping, category assignment, blocklist, dedupe, naming)
independently correct and testable without a native geospatial dependency in the Django app.
See ``atlas/data/osm_tag_map.json`` for the mapping and per-island blocklist, and place the
extract at ``atlas/data/osm_extract_<island>.json``. Missing extract → zero rows, not an error;
useful in dev before that pipeline exists.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from atlas.importers.base import BaseImporter, ImportRow
from atlas.models import AtlasPoi
from shared.geo import haversine_km


def load_tag_map() -> dict[str, Any]:
    path = Path(__file__).resolve().parent.parent / 'data' / 'osm_tag_map.json'
    return json.loads(path.read_text(encoding='utf-8'))


UNNAMED_DROP_CATEGORIES = set(load_tag_map().get('unnamed_nodes_dropped_for', []))
DEDUPE_RADIUS_M = load_tag_map().get('dedupe_radius_m', 25)


def _format_address(tags: dict[str, str]) -> str | None:
    """Composes a single display line from OSM's separate addr:* tags — present on ~20% of
    tagged elements (mostly food/stay/shops), never captured before this. `addr:street` alone
    still reads fine without a housenumber; nothing is fabricated for what's missing."""
    street = tags.get('addr:street')
    if not street:
        return None
    number = tags.get('addr:housenumber')
    line = f'{street}, {number}' if number else street
    postcode = tags.get('addr:postcode')
    city = tags.get('addr:city')
    tail = ' '.join(part for part in (postcode, city) if part)
    return f'{line} — {tail}' if tail else line


def _external_refs(element: dict, tags: dict[str, str]) -> dict:
    """Contact/reference fields kept alongside a POI but not editorial content — the detail
    screen renders these as-is (SDD 07 §4). `contact:*` is the newer OSM convention for the
    same data `phone`/`website` carry on older tagging; either is worth keeping."""
    phone = tags.get('phone') or tags.get('contact:phone')
    website = tags.get('website') or tags.get('contact:website')
    address = _format_address(tags)
    return {
        'osmId': element['osm_id'],
        **({'phone': phone} if phone else {}),
        **({'website': website} if website else {}),
        **({'address': address} if address else {}),
    }


class OsmImporter(BaseImporter):
    SOURCE = AtlasPoi.SOURCE_OSM

    def __init__(self, island):
        super().__init__(island)
        self._centers_cache: list[tuple[str, float, float]] | None = None

    def extract_path(self) -> Path:
        return Path(__file__).resolve().parent.parent / 'data' / f'osm_extract_{self.island.key}.json'

    def _tag_map(self) -> dict[str, str]:
        return load_tag_map()['tag_map']

    def _blocklist(self) -> set[str]:
        return set(load_tag_map()['blocklist'].get(self.island.key, []))

    def _owns(self, lat: float, lon: float) -> bool:
        """Whether this element is closer to this importer's island than to any other.

        The extracts are fetched per island over a centre+radius bounding box, and in the
        central group those boxes overlap heavily — Pico's 25 km box swallows most of Faial and
        part of São Jorge. Without this, the same OSM node imports under two islands (835 of
        them did), so filtering the map to Pico showed Faial's restaurants. Nearest-centre is a
        crude proxy for a real containment test, but the islands are far enough apart relative
        to their size that the midpoint between two centres always falls in open ocean.
        """
        nearest, best = None, float('inf')
        for key, center_lat, center_lng in self._island_centers():
            distance = haversine_km(lat, lon, center_lat, center_lng)
            if distance < best:
                nearest, best = key, distance
        return nearest == self.island.key

    def _island_centers(self) -> list[tuple[str, float, float]]:
        """Cached — `rows()` calls `_owns` once per extract element (3,800 on São Miguel), and
        re-querying the nine islands each time would be 3,800 round trips per import."""
        from tenancy.models import Island

        if self._centers_cache is None:
            self._centers_cache = list(
                Island.objects.filter(feature_flags__atlas=True).values_list(
                    'key', 'center_lat', 'center_lng',
                ),
            )
        return self._centers_cache

    def _category_for_tags(self, tags: dict[str, str], blocklist: set[str]) -> str | None:
        for tag_expr, category_slug in self._tag_map().items():
            key, _, value = tag_expr.partition('=')
            if tags.get(key) != value:
                continue
            if tag_expr in blocklist:
                return None
            return category_slug
        return None

    def rows(self) -> Iterator[ImportRow]:
        path = self.extract_path()
        if not path.exists():
            return

        elements = json.loads(path.read_text(encoding='utf-8'))
        blocklist = self._blocklist()
        kept: list[tuple[float, float, ImportRow]] = []

        for element in elements:
            tags = element.get('tags') or {}
            category_slug = self._category_for_tags(tags, blocklist)
            if category_slug is None:
                continue

            name = tags.get('name:pt') or tags.get('name') or ''
            if not name and category_slug in UNNAMED_DROP_CATEGORIES:
                continue

            lat, lon = element['lat'], element['lon']
            if not self._owns(lat, lon):
                continue
            if self._is_duplicate(lat, lon, kept):
                continue

            row = ImportRow(
                ref=str(element['osm_id']),
                name={'pt': name, 'en': tags.get('name:en') or name},
                latitude=lat,
                longitude=lon,
                category_slug=category_slug,
                kind=AtlasPoi.KIND_POI,
                tier=AtlasPoi.TIER_STANDARD,
                opening_hours={'raw': tags['opening_hours']} if tags.get('opening_hours') else {},
                accessibility={'wheelchair': tags['wheelchair']} if tags.get('wheelchair') else {},
                external_refs=_external_refs(element, tags),
            )
            kept.append((lat, lon, row))
            yield row

    def _is_duplicate(
        self, lat: float, lon: float, kept: list[tuple[float, float, ImportRow]],
    ) -> bool:
        """OSM frequently carries the same feature as both a node and a building polygon
        centroid — collapse anything within the dedupe radius, keeping the first (richest,
        since elements are pre-sorted by tag count upstream if that matters)."""
        for kept_lat, kept_lon, _ in kept:
            if haversine_km(lat, lon, kept_lat, kept_lon) * 1000 <= DEDUPE_RADIUS_M:
                return True
        return False
