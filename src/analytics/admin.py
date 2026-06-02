from django.contrib import admin

from analytics.models import AnalyticsEvent, Stat


@admin.register(AnalyticsEvent)
class AnalyticsEventAdmin(admin.ModelAdmin):
    list_display = ('module', 'event_type', 'platform', 'locale', 'occurred_at')
    list_filter = ('module', 'event_type', 'platform')
    date_hierarchy = 'occurred_at'
    ordering = ('-occurred_at',)


@admin.register(Stat)
class StatAdmin(admin.ModelAdmin):
    list_display = ('id', 'request', 'origin', 'destination', 'platform', 'language', 'timestamp')
    list_filter = ('request', 'platform', 'language', 'type_of_day')
    search_fields = ('origin', 'destination', 'request')
    date_hierarchy = 'timestamp'
    list_per_page = 50
    show_full_result_count = False
    ordering = ('-timestamp', '-id')
