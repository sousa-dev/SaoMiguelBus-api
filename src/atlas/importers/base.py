"""Importer framework — the ownership rule lives here (SDD 02 §5.2.1).

Each importer may only write AtlasPoi/AtlasTrail rows carrying its own `source` value. This
closes three silent failure modes: the monthly OSM run reverting editorial work, the OSM run
deleting first-party rows because they're absent from the .pbf, and two importers fighting
over the same physical place. The DB CheckConstraint (tier='curated' requires source='curated')
covers one axis of this; `BaseImporter.upsert()` scoping every lookup to `source=self.SOURCE`
covers the rest — it makes it structurally impossible for `import_atlas --source osm` to
touch a row another importer created, because it never queries outside its own source.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Iterable, Iterator

from atlas.models import AtlasCategory, AtlasPoi
from atlas.services import assign_category, assign_parish
from tenancy.models import Island


@dataclasses.dataclass
class ImportRow:
    """One POI as an importer sees it, before it becomes an AtlasPoi row."""

    ref: str  # stable key from the origin system — idempotent re-import key
    name: dict[str, str]  # {'pt': …, 'en': …}
    latitude: float
    longitude: float
    category_slug: str
    kind: str = AtlasPoi.KIND_POI
    tier: str = AtlasPoi.TIER_STANDARD
    description: dict[str, str] = dataclasses.field(default_factory=dict)
    elevation_m: int | None = None
    media: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    opening_hours: dict[str, Any] = dataclasses.field(default_factory=dict)
    tips: dict[str, Any] = dataclasses.field(default_factory=dict)
    accessibility: dict[str, Any] = dataclasses.field(default_factory=dict)
    external_refs: dict[str, Any] = dataclasses.field(default_factory=dict)


class BaseImporter:
    """Subclasses set SOURCE and implement rows(). Everything else is shared upsert logic."""

    SOURCE: str = ''

    def __init__(self, island: Island):
        if not self.SOURCE:
            raise NotImplementedError(f'{type(self).__name__} must set SOURCE')
        self.island = island
        self._category_cache: dict[str, AtlasCategory] = {}

    def rows(self) -> Iterable[ImportRow]:
        raise NotImplementedError

    def _category(self, slug: str) -> AtlasCategory:
        if slug not in self._category_cache:
            self._category_cache[slug] = AtlasCategory.objects.get(island=self.island, slug=slug)
        return self._category_cache[slug]

    def upsert(self, row: ImportRow) -> tuple[AtlasPoi, bool]:
        """Create or update a row this importer owns. Never touches a row with a different
        `source` — the lookup itself is scoped to SOURCE, so there's nothing else to touch."""
        existing = AtlasPoi.objects.filter(
            island=self.island, source=self.SOURCE, source_ref=row.ref,
        ).first()

        poi = existing or AtlasPoi(island=self.island, source=self.SOURCE, source_ref=row.ref)
        created = existing is None

        moved = created or poi.latitude != row.latitude or poi.longitude != row.longitude
        poi.kind = row.kind
        poi.name = row.name
        poi.latitude = row.latitude
        poi.longitude = row.longitude
        poi.elevation_m = row.elevation_m
        poi.external_refs = row.external_refs
        assign_category(poi, self._category(row.category_slug))

        # Fields this importer owns outright — every re-import refreshes them.
        poi.opening_hours = row.opening_hours

        # Fields enrichment may have already written (SDD 02 §5.2.3) — set only on create,
        # never blown away by a routine re-import.
        if created:
            poi.tier = row.tier
            poi.description = row.description
            poi.media = row.media
            poi.tips = row.tips
            poi.accessibility = row.accessibility

        if moved:
            assign_parish(poi)

        from atlas.models import AtlasRevision

        poi.revision = AtlasRevision.next_for(self.island)
        poi.is_active = True
        poi.is_published = not poi.is_safety_critical or poi.is_safety_reviewed
        poi.save()
        return poi, created

    def run(self) -> dict[str, int]:
        seen_refs: set[str] = set()
        created = updated = 0
        for row in self.rows():
            seen_refs.add(row.ref)
            _, was_created = self.upsert(row)
            if was_created:
                created += 1
            else:
                updated += 1

        tombstoned = self._tombstone_vanished(seen_refs)
        return {'created': created, 'updated': updated, 'tombstoned': tombstoned}

    def _tombstone_vanished(self, seen_refs: set[str]) -> int:
        """Rows this importer owns that no longer appear upstream get unpublished + tombstoned
        — scoped to `source=self.SOURCE`, so this can never retire another importer's rows."""
        from atlas.services import unpublish

        vanished = AtlasPoi.objects.filter(
            island=self.island, source=self.SOURCE, is_active=True,
        ).exclude(source_ref__in=seen_refs)

        count = 0
        for poi in vanished:
            unpublish(poi)
            poi.is_active = False
            poi.save(update_fields=['is_active'])
            count += 1
        return count
