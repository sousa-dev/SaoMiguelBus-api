from django.contrib import admin, messages
from django.utils.html import format_html

from tenancy.models import AppReleaseConfig, Island, LegacyImportJob
from tenancy.legacy_import_jobs import enqueue_import_job


@admin.register(Island)
class IslandAdmin(admin.ModelAdmin):
    list_display = ('key', 'name', 'archipelago', 'is_live', 'updated_at')
    list_filter = ('is_live', 'archipelago')
    search_fields = ('key', 'name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(LegacyImportJob)
class LegacyImportJobAdmin(admin.ModelAdmin):
    list_display = (
        'job_id',
        'status',
        'island_key',
        'current_step',
        'started_at',
        'finished_at',
    )
    list_filter = ('status', 'island_key')
    search_fields = ('job_id', 'export_file_path', 'celery_task_id')
    readonly_fields = (
        'job_id',
        'status',
        'island_key',
        'export_file_path',
        'legacy_db_url',
        'skip_steps',
        'current_step',
        'step_reports',
        'table_counts',
        'celery_task_id',
        'error',
        'started_at',
        'finished_at',
    )
    actions = ['enqueue_selected_jobs']

    @admin.action(description='Enqueue selected pending/failed jobs on Celery')
    def enqueue_selected_jobs(self, request, queryset):
        queued = 0
        for job in queryset:
            if job.status not in (
                LegacyImportJob.STATUS_PENDING,
                LegacyImportJob.STATUS_FAILED,
            ):
                continue
            job.status = LegacyImportJob.STATUS_PENDING
            job.error = ''
            job.save(update_fields=['status', 'error'])
            enqueue_import_job(job)
            queued += 1
        self.message_user(request, f'Queued {queued} import job(s) on Celery.', messages.SUCCESS)

    def has_add_permission(self, request):
        return False

    def error_preview(self, obj: LegacyImportJob) -> str:
        if not obj.error:
            return '—'
        preview = obj.error[:500]
        if len(obj.error) > 500:
            preview += '…'
        return format_html('<pre style="white-space:pre-wrap">{}</pre>', preview)

    error_preview.short_description = 'Error'


@admin.register(AppReleaseConfig)
class AppReleaseConfigAdmin(admin.ModelAdmin):
    list_display = (
        'island',
        'ios_current_version',
        'android_current_version',
        'ios_update_mode',
        'android_update_mode',
        'updated_at',
    )
    list_filter = ('ios_update_mode', 'android_update_mode')
    search_fields = ('island__key', 'island__name')
    readonly_fields = ('updated_at',)
    autocomplete_fields = ('island',)
    fieldsets = (
        (None, {'fields': ('island', 'updated_at')}),
        (
            'iOS',
            {
                'fields': (
                    'ios_current_version',
                    'ios_update_mode',
                    'ios_store_url',
                ),
            },
        ),
        (
            'Android',
            {
                'fields': (
                    'android_current_version',
                    'android_update_mode',
                    'android_store_url',
                ),
            },
        ),
    )
