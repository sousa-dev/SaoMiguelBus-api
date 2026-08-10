"""Atlas admin — POI map preview, bulk publish, safety review, tile pack rebuild (SDD 02 §5.1)."""

from __future__ import annotations

from django.contrib import admin
from django.utils.html import format_html

from atlas.models import (
    AtlasCategory,
    AtlasPoi,
    AtlasRevision,
    AtlasTombstone,
    AtlasTrail,
    AtlasTrailStage,
)
from atlas.services import publish, unpublish


@admin.register(AtlasCategory)
class AtlasCategoryAdmin(admin.ModelAdmin):
    list_display = ('slug', 'group', 'island', 'is_safety_critical', 'is_active', 'sort_order')
    list_filter = ('island', 'group', 'is_safety_critical', 'is_active')
    search_fields = ('slug',)
    ordering = ('island', 'sort_order', 'slug')


@admin.register(AtlasPoi)
class AtlasPoiAdmin(admin.ModelAdmin):
    list_display = (
        'display_name', 'category', 'tier', 'source', 'island',
        'is_safety_critical', 'is_safety_reviewed', 'is_published', 'revision',
    )
    list_filter = (
        'island', 'category', 'tier', 'source', 'is_safety_critical',
        'is_safety_reviewed', 'is_published', 'is_active',
    )
    search_fields = ('source_ref', 'uid')
    readonly_fields = ('uid', 'parish_slug', 'revision', 'updated_at', 'map_preview')
    actions = ['action_publish', 'action_unpublish', 'action_mark_safety_reviewed']

    fieldsets = (
        (None, {'fields': ('island', 'uid', 'category', 'kind', 'tier', 'source', 'source_ref')}),
        ('Content', {'fields': ('name', 'description', 'media', 'opening_hours', 'tips', 'accessibility')}),
        ('Location', {'fields': ('latitude', 'longitude', 'elevation_m', 'parish_slug', 'map_preview')}),
        ('AI enrichment', {'fields': ('enriched_at', 'enrichment_model')}),
        ('Safety review (D16)', {'fields': ('is_safety_critical', 'is_safety_reviewed')}),
        ('Status', {'fields': ('is_active', 'is_published', 'revision', 'updated_at')}),
    )

    @admin.display(description='Name')
    def display_name(self, obj: AtlasPoi) -> str:
        return obj.name.get('en') or obj.name.get('pt') or str(obj.uid)

    @admin.display(description='Map')
    def map_preview(self, obj: AtlasPoi) -> str:
        if not obj.pk:
            return '—'
        url = f'https://www.openstreetmap.org/?mlat={obj.latitude}&mlon={obj.longitude}#map=17/{obj.latitude}/{obj.longitude}'
        return format_html('<a href="{}" target="_blank" rel="noopener">View on OpenStreetMap ↗</a>', url)

    @admin.action(description='Publish selected POIs')
    def action_publish(self, request, queryset):
        blocked = 0
        for poi in queryset:
            if poi.is_safety_critical and not poi.is_safety_reviewed:
                blocked += 1
                continue
            publish(poi)
        if blocked:
            self.message_user(
                request,
                f'{blocked} safety-critical POI(s) skipped — review them first (D16).',
                level='warning',
            )

    @admin.action(description='Unpublish selected POIs')
    def action_unpublish(self, request, queryset):
        for poi in queryset:
            unpublish(poi)

    @admin.action(description='Mark safety-reviewed (does not publish)')
    def action_mark_safety_reviewed(self, request, queryset):
        queryset.update(is_safety_reviewed=True)


@admin.register(AtlasTrail)
class AtlasTrailAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'difficulty', 'distance_km', 'source', 'island', 'is_published')
    list_filter = ('island', 'source', 'difficulty', 'is_published', 'is_active')
    search_fields = ('source_ref', 'uid')
    readonly_fields = ('uid', 'revision', 'updated_at')

    @admin.display(description='Name')
    def display_name(self, obj: AtlasTrail) -> str:
        return obj.name.get('en') or obj.name.get('pt') or str(obj.uid)


@admin.register(AtlasTrailStage)
class AtlasTrailStageAdmin(admin.ModelAdmin):
    list_display = ('trail', 'sequence', 'island')
    list_filter = ('island',)


@admin.register(AtlasTombstone)
class AtlasTombstoneAdmin(admin.ModelAdmin):
    list_display = ('entity_type', 'entity_uid', 'source', 'island', 'revision', 'created_at')
    list_filter = ('island', 'entity_type', 'source')
    search_fields = ('entity_uid',)


@admin.register(AtlasRevision)
class AtlasRevisionAdmin(admin.ModelAdmin):
    list_display = ('island', 'current', 'updated_at')
    readonly_fields = ('island', 'current', 'updated_at')

    def has_add_permission(self, request):
        return False
