from django.contrib import admin

from seismic.models import FeltReport, SeismicEvent


@admin.register(SeismicEvent)
class SeismicEventAdmin(admin.ModelAdmin):
    list_display = ('emsc_id', 'magnitude', 'occurred_at', 'island', 'region')
    list_filter = ('island',)
    search_fields = ('emsc_id', 'region')


@admin.register(FeltReport)
class FeltReportAdmin(admin.ModelAdmin):
    list_display = ('event', 'intensity', 'island', 'reported_at')
    list_filter = ('island', 'intensity')
