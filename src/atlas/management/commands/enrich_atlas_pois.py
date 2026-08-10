"""AI enrichment pass over tier='standard' AtlasPoi rows, any source (SDD 02 §5.2.3, 00 D16).

Field ownership is enforced here, not just documented: this command writes description, tips,
media, accessibility, tier, enriched_at, and enrichment_model — nothing else. It never touches
source, source_ref, category, latitude, longitude, or name, so it can never collide with what
an importer owns, and a subsequent OSM/transit/minibus/trails re-import can never blow this
work away (those importers only set description/tips/media/accessibility on *create* — see
atlas/importers/base.py).

Safety-critical rows (is_safety_critical=True) are written here like any other, but the DB
constraint (atlas_safety_critical_requires_review_before_publish) makes it structurally
impossible for this command to publish one — is_published stays False until a human sets
is_safety_reviewed=True via admin.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from atlas.enrichment import load_provider
from atlas.models import AtlasPoi, AtlasRevision
from tenancy.models import Island


class Command(BaseCommand):
    help = "Enrich tier='standard' AtlasPoi rows toward tier='enriched' using the configured provider."

    def add_arguments(self, parser):
        parser.add_argument('--island', required=True, help='Island key, e.g. sao-miguel')
        parser.add_argument('--limit', type=int, default=None, help='Cap rows processed this run')

    def handle(self, *args, **options):
        island = Island.objects.filter(key=options['island']).first()
        if island is None:
            raise CommandError(f'Island not found: {options["island"]}')

        provider = load_provider()
        queryset = AtlasPoi.objects.filter(
            island=island, tier=AtlasPoi.TIER_STANDARD, is_active=True,
        ).order_by('id')
        if options['limit']:
            queryset = queryset[: options['limit']]

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

        self.stdout.write(
            self.style.SUCCESS(
                f'enrich_atlas_pois island={island.key} provider={provider.model_name}: '
                f'{enriched} enriched, {skipped} skipped',
            ),
        )
