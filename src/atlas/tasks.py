"""Atlas Celery tasks — monthly import, AI enrichment, seed-DB build.

No tile tasks: the basemap is a static file bundled into the app, not built or served
here (SDD 00 D17, 01 §3).
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name='atlas.import_all_sources')
def import_all_sources_task(island_key: str | None = None) -> dict:
    """Monthly refresh: run every importer for every live island (or one), in ownership order.

    `osm` runs last deliberately — not that order matters for correctness (each importer is
    scoped to its own `source`), but running first-party importers first means a fresh install
    or a stuck OSM extract still leaves the higher-trust rows current.
    """
    from atlas.importers import IMPORTER_REGISTRY
    from tenancy.models import Island

    islands = Island.objects.filter(is_live=True, feature_flags__atlas=True)
    if island_key:
        islands = islands.filter(key=island_key)

    order = ['transit', 'minibus', 'trails', 'curated', 'osm']
    totals: dict[str, dict] = {}
    for island in islands:
        island_totals = {}
        for source in order:
            importer = IMPORTER_REGISTRY[source](island)
            island_totals[source] = importer.run()
        totals[island.key] = island_totals
        logger.info('atlas.import_all_sources island=%s totals=%s', island.key, island_totals)

    return {'status': 'ok', 'islands': totals}


@shared_task(name='atlas.enrich_pois')
def enrich_pois_task(island_key: str | None = None, limit: int | None = None) -> dict:
    from atlas.enrichment import load_provider
    from atlas.models import AtlasPoi, AtlasRevision
    from django.utils import timezone
    from tenancy.models import Island

    islands = Island.objects.filter(is_live=True, feature_flags__atlas=True)
    if island_key:
        islands = islands.filter(key=island_key)

    provider = load_provider()
    totals: dict[str, dict] = {}
    for island in islands:
        queryset = AtlasPoi.objects.filter(
            island=island, tier=AtlasPoi.TIER_STANDARD, is_active=True,
        ).order_by('id')
        if limit:
            queryset = queryset[:limit]

        enriched = skipped = 0
        for poi in queryset:
            result = provider.enrich(poi)
            if result is None:
                skipped += 1
                continue
            poi.description = result.description
            poi.tips = result.tips
            poi.media = result.media
            poi.accessibility = result.accessibility
            poi.tier = AtlasPoi.TIER_ENRICHED
            poi.enriched_at = timezone.now()
            poi.enrichment_model = provider.model_name
            poi.revision = AtlasRevision.next_for(island)
            poi.save(update_fields=[
                'description', 'tips', 'media', 'accessibility',
                'tier', 'enriched_at', 'enrichment_model', 'revision',
            ])
            enriched += 1

        totals[island.key] = {'enriched': enriched, 'skipped': skipped}
        logger.info('atlas.enrich_pois island=%s enriched=%s skipped=%s', island.key, enriched, skipped)

    return {'status': 'ok', 'provider': provider.model_name, 'islands': totals}


@shared_task(name='atlas.build_seed_db')
def build_seed_db_task(output: str = 'media/atlas/atlas-seed.db') -> dict:
    from pathlib import Path

    from atlas.seed_db import build_seed_db

    counts = build_seed_db(Path(output))
    logger.info('atlas.build_seed_db output=%s counts=%s', output, counts)
    return {'status': 'ok', 'output': output, 'counts': counts}
