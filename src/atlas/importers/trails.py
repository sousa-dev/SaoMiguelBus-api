"""Trails, stages, and trailhead POIs from our own trails app (SDD 07 §4b). Read-only —
atlas never writes back to trails.Trail. Two entity kinds come out of the same source:
AtlasTrail (+ AtlasTrailStage) for the routes themselves, and AtlasPoi for trailhead markers
(trails.POI). They share SOURCE_TRAILS but are different tables, so this module has two
importer classes rather than forcing both into BaseImporter's POI-only upsert.
"""

from __future__ import annotations

from typing import Iterator

from atlas.identifiers import atlas_trail_uid
from atlas.importers.base import BaseImporter, ImportRow
from atlas.models import AtlasPoi, AtlasRevision, AtlasTrail, AtlasTrailStage
from atlas.services import assign_parish
from tenancy.models import Island
from trails.models import POI as TrailsPoi
from trails.models import Trail as TrailsTrail
from trails.models import TrailStage as TrailsTrailStage


class TrailheadPoiImporter(BaseImporter):
    """trails.POI → AtlasPoi. Category mapping is a placeholder (trails.POI.category is free
    text from the VisitAzores source, not our taxonomy) — everything lands as 'trailhead' with
    kind=trailhead until someone maps the real category strings seen in production data."""

    SOURCE = AtlasPoi.SOURCE_TRAILS

    def rows(self) -> Iterator[ImportRow]:
        for poi in TrailsPoi.objects.filter(island=self.island).order_by('name'):
            yield ImportRow(
                ref=poi.source_ref,
                name={'pt': poi.name, 'en': poi.name},
                latitude=poi.latitude,
                longitude=poi.longitude,
                category_slug='trailhead',
                kind=AtlasPoi.KIND_TRAILHEAD,
                tier=AtlasPoi.TIER_STANDARD,
                external_refs={'trailsPoiId': poi.pk, 'trailsCategory': poi.category},
            )


class TrailsImporter:
    """trails.Trail / TrailStage → AtlasTrail / AtlasTrailStage. Field mapping per SDD 07 §4b."""

    SOURCE = AtlasTrail.SOURCE_TRAILS

    def __init__(self, island: Island):
        self.island = island

    def run(self) -> dict[str, int]:
        seen_refs: set[str] = set()
        created = updated = 0

        for trail in TrailsTrail.objects.filter(island=self.island).order_by('name'):
            seen_refs.add(trail.source_ref)
            _, was_created = self._upsert(trail)
            created += was_created
            updated += not was_created

        tombstoned = self._tombstone_vanished(seen_refs)

        poi_result = TrailheadPoiImporter(self.island).run()
        return {
            'trails_created': created,
            'trails_updated': updated,
            'trails_tombstoned': tombstoned,
            **{f'pois_{k}': v for k, v in poi_result.items()},
        }

    def _upsert(self, source_trail: TrailsTrail) -> tuple[AtlasTrail, bool]:
        existing = AtlasTrail.objects.filter(
            island=self.island, source=self.SOURCE, source_ref=source_trail.source_ref,
        ).first()
        if existing is None:
            trail = AtlasTrail(
                island=self.island,
                source=self.SOURCE,
                source_ref=source_trail.source_ref,
                # Deterministic uid shared with the Expo release bundler — assigned only on
                # create so re-imports never rewrite an already-synced identity.
                uid=atlas_trail_uid(self.island.key, source_trail.source_ref),
            )
            created = True
        else:
            trail = existing
            created = False
        moved = created or trail.start_lat != source_trail.start_lat or trail.start_lon != source_trail.start_lon

        trail.name = {'pt': source_trail.name, 'en': source_trail.name}
        trail.description = {'pt': source_trail.description_pt, 'en': source_trail.description_en}
        trail.difficulty = source_trail.difficulty
        trail.distance_km = source_trail.distance_km
        trail.duration_min = source_trail.duration_min
        trail.shape = source_trail.shape
        trail.start_lat = source_trail.start_lat
        trail.start_lon = source_trail.start_lon
        trail.geojson = source_trail.geojson
        trail.gpx_url = source_trail.gpx_url
        trail.payload = {
            'waypoints': source_trail.waypoints,
            'downloads': {'gpx': source_trail.gpx_url, 'kml': source_trail.kml_url},
            'media': {'mapImage': source_trail.map_image_url, 'leaflet': source_trail.leaflet_url},
        }

        if moved and trail.start_lat is not None and trail.start_lon is not None:
            assign_parish(trail)

        trail.revision = AtlasRevision.next_for(self.island)
        trail.is_active = True
        trail.is_published = True
        trail.save()

        self._sync_stages(trail, source_trail)
        return trail, created

    def _sync_stages(self, trail: AtlasTrail, source_trail: TrailsTrail) -> None:
        AtlasTrailStage.objects.filter(island=self.island, trail=trail).delete()
        stages = TrailsTrailStage.objects.filter(island=self.island, trail=source_trail).order_by('sequence')
        AtlasTrailStage.objects.bulk_create([
            AtlasTrailStage(
                island=self.island,
                trail=trail,
                name={'pt': stage.name, 'en': stage.name},
                sequence=stage.sequence,
                geojson=stage.geojson,
            )
            for stage in stages
        ])

    def _tombstone_vanished(self, seen_refs: set[str]) -> int:
        from atlas.services import write_tombstone

        vanished = AtlasTrail.objects.filter(
            island=self.island, source=self.SOURCE, is_active=True,
        ).exclude(source_ref__in=seen_refs)

        count = 0
        for trail in vanished:
            revision = AtlasRevision.next_for(self.island)
            trail.is_active = False
            trail.is_published = False
            trail.revision = revision
            trail.save(update_fields=['is_active', 'is_published', 'revision'])
            write_tombstone(trail, revision=revision)
            count += 1
        return count
