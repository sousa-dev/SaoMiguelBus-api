"""Hand-written editorial content, version-controlled in atlas/data/curated_<island>.json.

Not a launch dependency (SDD 00 D13, §7.1) — the file ships empty per island and stays that
way until someone writes into it. When it does have rows, this is the one importer that can
produce tier='curated', and the DB constraint (atlas_curated_tier_requires_curated_source)
enforces that no other importer ever can.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from atlas.importers.base import BaseImporter, ImportRow
from atlas.models import AtlasPoi


class CuratedImporter(BaseImporter):
    SOURCE = AtlasPoi.SOURCE_CURATED

    def data_path(self) -> Path:
        return Path(__file__).resolve().parent.parent / 'data' / f'curated_{self.island.key}.json'

    def rows(self) -> Iterator[ImportRow]:
        path = self.data_path()
        if not path.exists():
            return
        rows = json.loads(path.read_text(encoding='utf-8'))
        for row in rows:
            yield ImportRow(
                ref=row['ref'],
                name=row['name'],
                latitude=row['latitude'],
                longitude=row['longitude'],
                category_slug=row['category'],
                kind=row.get('kind', AtlasPoi.KIND_POI),
                tier=AtlasPoi.TIER_CURATED,
                description=row.get('description', {}),
                elevation_m=row.get('elevationM'),
                media=row.get('media', []),
                opening_hours=row.get('openingHours', {}),
                tips=row.get('tips', {}),
                accessibility=row.get('accessibility', {}),
            )
