"""Atlas — offline map & guide catalogue (Ultimate Offline Azores Map & Guide).

See SDD 02-api-database-schema.md for the full design. Notable deviation from that doc's
pseudocode: the safety-review publish gate is enforced against a denormalised
``AtlasPoi.is_safety_critical`` boolean rather than ``category__slug__in=[...]`` directly,
because a Postgres CHECK constraint cannot reference a joined table's columns.
"""

from __future__ import annotations

import uuid

from django.db import models, transaction

from tenancy.models import Island, TenantScopedModel


class AtlasRevision(models.Model):
    """Monotonic per-island revision counter. One row per island. Backbone of delta sync."""

    island = models.OneToOneField(Island, on_delete=models.CASCADE, related_name='atlas_revision')
    current = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Atlas revision'
        verbose_name_plural = 'Atlas revisions'

    def __str__(self) -> str:
        return f'{self.island.key} @ {self.current}'

    @classmethod
    def next_for(cls, island: Island) -> int:
        """Allocate the next revision. Safe to call inside or outside an existing transaction."""
        with transaction.atomic():
            row, _ = cls.objects.select_for_update().get_or_create(island=island)
            row.current += 1
            row.save(update_fields=['current', 'updated_at'])
            return row.current


class AtlasCategory(TenantScopedModel):
    GROUP_NATURE = 'nature'
    GROUP_ACTIVE = 'active'
    GROUP_CULTURE = 'culture'
    GROUP_WELLNESS = 'wellness'
    GROUP_PRACTICAL = 'practical'
    GROUP_FOOD_STAY = 'food_stay'
    GROUP_TRANSPORT = 'transport'
    GROUP_EMERGENCY = 'emergency'
    GROUP_CHOICES = [
        (GROUP_NATURE, 'Nature'),
        (GROUP_ACTIVE, 'Active'),
        (GROUP_CULTURE, 'Culture'),
        (GROUP_WELLNESS, 'Wellness'),
        (GROUP_PRACTICAL, 'Practical'),
        (GROUP_FOOD_STAY, 'Food & stay'),
        (GROUP_TRANSPORT, 'Transport'),
        (GROUP_EMERGENCY, 'Emergency'),
    ]

    slug = models.SlugField(max_length=64)
    name = models.JSONField(default=dict)  # {'pt': 'Miradouros', 'en': 'Viewpoints', ...}
    group = models.CharField(max_length=32, choices=GROUP_CHOICES, default=GROUP_NATURE)
    icon = models.CharField(max_length=64, default='map-pin')  # lucide icon name
    color = models.CharField(max_length=9, default='#0B4F9E')
    sort_order = models.PositiveIntegerField(default=100)
    # Denormalisation target for AtlasPoi.is_safety_critical (D16) — set here once,
    # mirrored onto every POI in that category via services.assign_category().
    is_safety_critical = models.BooleanField(
        default=False,
        help_text='Natural pools, fumaroles, hot springs, volcanic caves — AI-written '
                   'safety text in this category requires human review before publish.',
    )
    is_active = models.BooleanField(default=True)
    revision = models.BigIntegerField(default=0, db_index=True)

    class Meta:
        unique_together = [('island', 'slug')]
        ordering = ['sort_order', 'slug']
        verbose_name_plural = 'Atlas categories'

    def __str__(self) -> str:
        return self.slug


class AtlasPoi(TenantScopedModel):
    KIND_POI = 'poi'
    KIND_VIEWPOINT = 'viewpoint'
    KIND_TRAILHEAD = 'trailhead'
    KIND_BEACH = 'beach'
    KIND_CHOICES = [
        (KIND_POI, 'POI'),
        (KIND_VIEWPOINT, 'Viewpoint'),
        (KIND_TRAILHEAD, 'Trailhead'),
        (KIND_BEACH, 'Beach'),
    ]

    # Editorial level — drives the "Highlights only" filter. Three tiers (D13): 'standard' is
    # the raw import, 'enriched' is AI-written on top of it (any source), 'curated' is
    # hand-written and requires source='curated' (enforced below). Highlights = enriched + curated.
    TIER_CURATED = 'curated'
    TIER_ENRICHED = 'enriched'
    TIER_STANDARD = 'standard'
    TIER_CHOICES = [
        (TIER_CURATED, 'Curated'),
        (TIER_ENRICHED, 'Enriched'),
        (TIER_STANDARD, 'Standard'),
    ]

    # Provenance — drives import ownership. Two orthogonal axes, deliberately separate: a
    # first-party bus stop is `standard` tier but is NOT from OSM.
    SOURCE_CURATED = 'curated'
    SOURCE_OSM = 'osm'
    SOURCE_TRANSIT = 'transit'
    SOURCE_MINIBUS = 'minibus'
    SOURCE_TRAILS = 'trails'
    SOURCE_CHOICES = [
        (SOURCE_CURATED, 'Curated'),
        (SOURCE_OSM, 'OpenStreetMap'),
        (SOURCE_TRANSIT, 'Transit (first-party)'),
        (SOURCE_MINIBUS, 'Mini Bus (first-party)'),
        (SOURCE_TRAILS, 'Trails (first-party)'),
    ]

    uid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    category = models.ForeignKey(AtlasCategory, on_delete=models.PROTECT, related_name='pois')
    kind = models.CharField(max_length=32, choices=KIND_CHOICES, default=KIND_POI)
    tier = models.CharField(max_length=16, choices=TIER_CHOICES, default=TIER_STANDARD, db_index=True)
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES, default=SOURCE_OSM, db_index=True)
    # Stable key from the originating system — transit's cleaned_name, minibus's external_id,
    # the OSM node id. Used for idempotent re-import and exact Hub deep links.
    source_ref = models.CharField(max_length=200, blank=True, default='', db_index=True)
    name = models.JSONField(default=dict)  # {'pt': …, 'en': …}
    description = models.JSONField(default=dict, blank=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    elevation_m = models.IntegerField(null=True, blank=True)

    # Denormalised parish link for offline microclimate (D6).
    parish = models.ForeignKey(
        'weather.Parish', null=True, blank=True, on_delete=models.SET_NULL, related_name='atlas_pois',
    )
    parish_slug = models.SlugField(max_length=160, blank=True, default='', db_index=True)

    # Editorial
    media = models.JSONField(default=list, blank=True)  # [{url, credit, licence}]
    opening_hours = models.JSONField(default=dict, blank=True)
    tips = models.JSONField(default=dict, blank=True)
    accessibility = models.JSONField(default=dict, blank=True)
    external_refs = models.JSONField(default=dict, blank=True)  # {'trails_poi_id': 42, …}

    # AI enrichment tracking (D16) — orthogonal to `source`. Never written by an importer;
    # only by the enrichment task and, for is_safety_reviewed, by a human via admin.
    enriched_at = models.DateTimeField(null=True, blank=True)
    enrichment_model = models.CharField(max_length=64, blank=True, default='')  # e.g. 'claude-sonnet-5'
    # Denormalised from category.is_safety_critical at category-assignment time — see
    # services.assign_category(). Kept on the row itself so the publish-gate CheckConstraint
    # below can reference it directly (a constraint cannot join to AtlasCategory).
    is_safety_critical = models.BooleanField(default=False)
    is_safety_reviewed = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)
    is_published = models.BooleanField(default=False)
    revision = models.BigIntegerField(default=0, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']
        indexes = [
            models.Index(fields=['island', 'revision']),  # the sync query
            models.Index(fields=['island', 'is_published', 'is_active']),
            models.Index(fields=['island', 'latitude', 'longitude']),
        ]
        constraints = [
            models.CheckConstraint(
                check=~(models.Q(tier='curated') & ~models.Q(source='curated')),
                name='atlas_curated_tier_requires_curated_source',
            ),
            models.CheckConstraint(
                check=~(
                    models.Q(is_published=True)
                    & models.Q(is_safety_critical=True)
                    & models.Q(is_safety_reviewed=False)
                ),
                name='atlas_safety_critical_requires_review_before_publish',
            ),
        ]
        verbose_name = 'Atlas POI'

    def __str__(self) -> str:
        return self.name.get('en') or self.name.get('pt') or str(self.uid)


class AtlasTrail(TenantScopedModel):
    SOURCE_CURATED = 'curated'
    SOURCE_TRAILS = 'trails'
    SOURCE_CHOICES = [
        (SOURCE_CURATED, 'Curated'),
        (SOURCE_TRAILS, 'Trails (first-party)'),
    ]

    uid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES, default=SOURCE_TRAILS, db_index=True)
    source_ref = models.CharField(max_length=200, blank=True, default='', db_index=True)
    name = models.JSONField(default=dict)
    description = models.JSONField(default=dict, blank=True)
    difficulty = models.CharField(max_length=32, blank=True, default='')
    distance_km = models.FloatField(null=True, blank=True)
    duration_min = models.PositiveIntegerField(null=True, blank=True)
    ascent_m = models.IntegerField(null=True, blank=True)
    shape = models.CharField(max_length=32, blank=True, default='')
    start_lat = models.FloatField(null=True, blank=True)
    start_lon = models.FloatField(null=True, blank=True)
    parish = models.ForeignKey(
        'weather.Parish', null=True, blank=True, on_delete=models.SET_NULL, related_name='atlas_trails',
    )
    parish_slug = models.SlugField(max_length=160, blank=True, default='', db_index=True)
    # LineString, Douglas-Peucker simplified server-side (~10m) — see AtlasTrail.gpx_url for
    # the unsimplified original.
    geojson = models.JSONField(default=dict, blank=True)
    gpx_url = models.CharField(max_length=500, blank=True, default='')
    payload = models.JSONField(default=dict, blank=True)  # waypoints, downloads, media
    is_active = models.BooleanField(default=True)
    is_published = models.BooleanField(default=False)
    revision = models.BigIntegerField(default=0, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']
        indexes = [
            models.Index(fields=['island', 'revision']),
            models.Index(fields=['island', 'is_published', 'is_active']),
        ]
        verbose_name = 'Atlas trail'

    def __str__(self) -> str:
        return self.name.get('en') or self.name.get('pt') or str(self.uid)


class AtlasTrailStage(TenantScopedModel):
    trail = models.ForeignKey(AtlasTrail, on_delete=models.CASCADE, related_name='stages')
    name = models.JSONField(default=dict)
    sequence = models.PositiveIntegerField(default=1)
    geojson = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['sequence']
        verbose_name = 'Atlas trail stage'

    def __str__(self) -> str:
        label = self.name.get('en') or self.name.get('pt') or f'stage {self.sequence}'
        return f'{self.trail} — {label}'


class AtlasTombstone(TenantScopedModel):
    ENTITY_POI = 'poi'
    ENTITY_TRAIL = 'trail'
    ENTITY_CATEGORY = 'category'
    ENTITY_CHOICES = [
        (ENTITY_POI, 'POI'),
        (ENTITY_TRAIL, 'Trail'),
        (ENTITY_CATEGORY, 'Category'),
    ]

    entity_type = models.CharField(max_length=32, choices=ENTITY_CHOICES)
    entity_uid = models.UUIDField()
    # Provenance carried through so full_resync / importer tombstoning can stay scoped to
    # the source that owned the row, mirroring the import-ownership rule.
    source = models.CharField(max_length=16, blank=True, default='')
    revision = models.BigIntegerField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['island', 'revision'])]
        verbose_name = 'Atlas tombstone'

    def __str__(self) -> str:
        return f'{self.entity_type}:{self.entity_uid} @ {self.revision}'
