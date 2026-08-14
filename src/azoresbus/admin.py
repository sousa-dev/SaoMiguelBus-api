"""Admin for the AzoresBus sync — the primary way to check "is it working?".

SyncRun is the one to watch: status/started_at/finished_at/request_count answer
whether a run happened, how long it took and whether it hit its budget.
`stats` (not list_display'able, but visible on the detail page) carries the
per-entity counts and the retirement decision.
"""

from __future__ import annotations

from django.contrib import admin

from azoresbus.models import (
    ExternalJourney,
    ExternalStop,
    ServiceObservation,
    SyncRun,
    TariffSnapshot,
)


@admin.register(SyncRun)
class SyncRunAdmin(admin.ModelAdmin):
    list_display = (
        'started_at', 'kind', 'status', 'island', 'request_count', 'finished_at',
    )
    list_filter = ('island', 'kind', 'status')
    ordering = ('-started_at',)
    readonly_fields = (
        'island', 'kind', 'status', 'started_at', 'finished_at',
        'request_count', 'sampled_dates', 'stats', 'error',
    )
    date_hierarchy = 'started_at'

    def has_add_permission(self, request):
        # Written only by the sync itself; a hand-created row would be
        # indistinguishable from a real run's evidence.
        return False


@admin.register(ExternalStop)
class ExternalStopAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'external_id', 'dataset', 'island', 'stop')
    list_filter = ('island', 'dataset')
    search_fields = ('code', 'name', 'external_id')
    raw_id_fields = ('stop',)
    list_per_page = 100


@admin.register(ExternalJourney)
class ExternalJourneyAdmin(admin.ModelAdmin):
    list_display = (
        'external_id', 'route_ext_id', 'direction', 'dataset', 'island', 'trip',
    )
    list_filter = ('island', 'dataset')
    search_fields = ('external_id', 'route_ext_id', 'identity')
    raw_id_fields = ('trip',)
    list_per_page = 100


@admin.register(ServiceObservation)
class ServiceObservationAdmin(admin.ModelAdmin):
    list_display = ('external_id', 'date', 'dataset', 'island', 'run')
    list_filter = ('island', 'dataset', 'date')
    search_fields = ('external_id',)
    raw_id_fields = ('run',)
    list_per_page = 100

    def has_add_permission(self, request):
        return False


@admin.register(TariffSnapshot)
class TariffSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        'effective_date', 'is_current', 'content_hash', 'fetched_at', 'island',
    )
    list_filter = ('island', 'is_current')
    ordering = ('-effective_date', '-fetched_at')
    readonly_fields = ('content_hash', 'payload', 'fetched_at')

    def has_add_permission(self, request):
        return False
