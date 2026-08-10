"""Build assets/atlas-seed.db — the SQLite file bundled into the Expo binary.

Schema mirrors the client's own (SDD 01 §5.2) exactly, so the app's migration runner never has
to reconcile a divergent seed shape. Archipelago-wide (SDD 01 §5.3): all nine islands' published
rows go in, not just São Miguel's — the full catalogue is ~10-20MB even at 17,000 POIs, cheap
enough to always bundle, so opening the app and browsing Pico's POIs works offline even before
that island's map tiles are downloaded.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from atlas.models import AtlasCategory, AtlasPoi, AtlasRevision, AtlasTrail, AtlasTrailStage

SCHEMA = """
CREATE TABLE poi (
  id            TEXT PRIMARY KEY,
  island        TEXT NOT NULL,
  category      TEXT NOT NULL,
  kind          TEXT NOT NULL,
  tier          TEXT NOT NULL,
  source        TEXT NOT NULL,
  source_ref    TEXT,
  name          TEXT NOT NULL,
  latitude      REAL NOT NULL,
  longitude     REAL NOT NULL,
  parish_slug   TEXT,
  elevation_m   INTEGER,
  payload       TEXT NOT NULL,
  revision      INTEGER NOT NULL,
  updated_at    TEXT NOT NULL
);
CREATE INDEX poi_bbox   ON poi(island, latitude, longitude);
CREATE INDEX poi_cat    ON poi(island, category);
CREATE INDEX poi_tier   ON poi(island, tier);
CREATE INDEX poi_parish ON poi(parish_slug);

CREATE VIRTUAL TABLE poi_fts USING fts5(
  id UNINDEXED, name, description, tokenize='unicode61 remove_diacritics 2'
);

CREATE TABLE category (
  slug TEXT NOT NULL, island TEXT NOT NULL, name_json TEXT,
  icon TEXT, color TEXT, sort_order INTEGER, "group" TEXT,
  PRIMARY KEY (island, slug)
);

CREATE TABLE trail (
  id TEXT PRIMARY KEY, island TEXT NOT NULL, name TEXT NOT NULL,
  source TEXT NOT NULL, source_ref TEXT,
  difficulty TEXT, distance_km REAL, duration_min INTEGER,
  ascent_m INTEGER, shape TEXT, start_lat REAL, start_lon REAL,
  parish_slug TEXT,
  geojson TEXT, gpx_uri TEXT,
  payload TEXT, revision INTEGER NOT NULL
);

CREATE TABLE trail_stage (
  id TEXT PRIMARY KEY,
  trail_id TEXT NOT NULL REFERENCES trail(id) ON DELETE CASCADE,
  name TEXT NOT NULL, sequence INTEGER NOT NULL, geojson TEXT
);
CREATE INDEX trail_stage_seq ON trail_stage(trail_id, sequence);

CREATE TABLE sync_state (
  island TEXT PRIMARY KEY,
  revision INTEGER NOT NULL DEFAULT 0,
  last_sync_at TEXT,
  last_error TEXT
);
"""


def _poi_name_text(name: dict) -> str:
    return ' '.join(v for v in name.values() if v)


def _pick_localized(name: dict) -> str:
    """pt-first display string — matches the sync client's own localisation fallback
    (pickLocalizedText in lib/atlas/localize.ts) so seed rows and synced rows agree on what
    `poi.name`/`trail.name` hold: flat display text, never a raw i18n dict."""
    return name.get('pt') or name.get('en') or next((v for v in name.values() if v), '')


def build_seed_db(output_path: Path) -> dict[str, int]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    conn = sqlite3.connect(output_path)
    try:
        conn.executescript(SCHEMA)

        counts = {'categories': 0, 'pois': 0, 'trails': 0, 'trail_stages': 0, 'islands': 0}

        islands = list(AtlasRevision.objects.select_related('island').all())
        counts['islands'] = len(islands)

        for row in AtlasCategory.objects.filter(is_active=True).select_related('island'):
            conn.execute(
                'INSERT INTO category (slug, island, name_json, icon, color, sort_order, "group") '
                'VALUES (?,?,?,?,?,?,?)',
                (row.slug, row.island.key, json.dumps(row.name), row.icon, row.color, row.sort_order, row.group),
            )
            counts['categories'] += 1

        for row in (
            AtlasPoi.objects.filter(is_published=True, is_active=True)
            .select_related('category', 'island')
        ):
            payload = json.dumps({
                'description': row.description,
                'media': row.media,
                'openingHours': row.opening_hours,
                'tips': row.tips,
                'accessibility': row.accessibility,
                'externalRefs': row.external_refs,
            })
            conn.execute(
                'INSERT INTO poi (id, island, category, kind, tier, source, source_ref, name, '
                'latitude, longitude, parish_slug, elevation_m, payload, revision, updated_at) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (
                    str(row.uid), row.island.key, row.category.slug, row.kind, row.tier,
                    row.source, row.source_ref, _pick_localized(row.name), row.latitude, row.longitude,
                    row.parish_slug, row.elevation_m, payload, row.revision, row.updated_at.isoformat(),
                ),
            )
            conn.execute(
                'INSERT INTO poi_fts (id, name, description) VALUES (?,?,?)',
                (str(row.uid), _poi_name_text(row.name), _poi_name_text(row.description)),
            )
            counts['pois'] += 1

        for row in (
            AtlasTrail.objects.filter(is_published=True, is_active=True).select_related('island')
        ):
            conn.execute(
                'INSERT INTO trail (id, island, name, source, source_ref, difficulty, distance_km, '
                'duration_min, ascent_m, shape, start_lat, start_lon, parish_slug, geojson, gpx_uri, '
                'payload, revision) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (
                    str(row.uid), row.island.key, _pick_localized(row.name), row.source, row.source_ref,
                    row.difficulty, row.distance_km, row.duration_min, row.ascent_m, row.shape,
                    row.start_lat, row.start_lon, row.parish_slug, json.dumps(row.geojson), row.gpx_url,
                    json.dumps(row.payload), row.revision,
                ),
            )
            counts['trails'] += 1
            for stage in AtlasTrailStage.objects.filter(trail=row).order_by('sequence'):
                conn.execute(
                    'INSERT INTO trail_stage (id, trail_id, name, sequence, geojson) VALUES (?,?,?,?,?)',
                    (
                        f'{row.uid}:{stage.sequence}', str(row.uid),
                        _pick_localized(stage.name), stage.sequence, json.dumps(stage.geojson),
                    ),
                )
                counts['trail_stages'] += 1

        for revision in islands:
            conn.execute(
                'INSERT INTO sync_state (island, revision) VALUES (?,?)',
                (revision.island.key, revision.current),
            )

        conn.commit()
    finally:
        conn.close()

    return counts
