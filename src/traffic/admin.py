from django.contrib import admin

from traffic.models import TrafficCategory, TrafficConfirmation, TrafficReport


def _expire(modeladmin, request, queryset):
    queryset.update(status=TrafficReport.EXPIRED)


_expire.short_description = 'Mark selected expired'


def _remove(modeladmin, request, queryset):
    queryset.update(status=TrafficReport.REMOVED)


_remove.short_description = 'Remove selected (takedown)'


@admin.register(TrafficCategory)
class TrafficCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'icon', 'default_ttl_minutes', 'is_schedulable', 'order', 'island')
    list_filter = ('island', 'is_schedulable')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(TrafficReport)
class TrafficReportAdmin(admin.ModelAdmin):
    list_display = (
        'category', 'status', 'road', 'expires_at',
        'confirm_count', 'deny_count', 'created_at', 'island',
    )
    list_filter = ('island', 'status', 'category')
    search_fields = ('description', 'road')
    actions = [_expire, _remove]


@admin.register(TrafficConfirmation)
class TrafficConfirmationAdmin(admin.ModelAdmin):
    list_display = ('report', 'vote', 'island', 'created_at')
    list_filter = ('island', 'vote')
