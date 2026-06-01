from django.contrib import admin, messages
from django.http import FileResponse, Http404
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils.html import format_html

from app.models import LegacyExportJob
from app.services.legacy_export import start_legacy_export_job


@admin.register(LegacyExportJob)
class LegacyExportJobAdmin(admin.ModelAdmin):
    change_list_template = 'admin/app/legacyexportjob/change_list.html'
    list_display = (
        'job_id',
        'status',
        'started_at',
        'finished_at',
        'exported_at',
        'download_link',
    )
    list_filter = ('status',)
    search_fields = ('job_id',)
    readonly_fields = (
        'job_id',
        'status',
        'started_at',
        'finished_at',
        'exported_at',
        'export_file',
        'table_counts',
        'error',
        'download_link',
    )
    ordering = ('-started_at',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def download_link(self, obj):
        if obj.status != LegacyExportJob.STATUS_COMPLETED or not obj.export_file:
            return '—'
        url = reverse('admin:app_legacyexportjob_download', args=[obj.pk])
        return format_html('<a class="button" href="{}">Download JSON</a>', url)

    download_link.short_description = 'Export file'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:object_id>/download/',
                self.admin_site.admin_view(self.download_export),
                name='app_legacyexportjob_download',
            ),
            path(
                'start/',
                self.admin_site.admin_view(self.start_export),
                name='app_legacyexportjob_start',
            ),
        ]
        return custom_urls + urls

    def download_export(self, request, object_id):
        job = self.get_object(request, object_id)
        if job is None or job.status != LegacyExportJob.STATUS_COMPLETED or not job.export_file:
            raise Http404('Export file not available')

        exported_on = (job.exported_at or job.finished_at or job.started_at).strftime('%Y-%m-%d')
        filename = f'smb_legacy_export_{exported_on}_{job.job_id[:8]}.json'
        return FileResponse(
            job.export_file.open('rb'),
            as_attachment=True,
            filename=filename,
            content_type='application/json; charset=utf-8',
        )

    def start_export(self, request):
        status = start_legacy_export_job()
        messages.success(
            request,
            f'Started export job {status["job_id"]} (status: {status["status"]}).',
        )
        return redirect('admin:app_legacyexportjob_changelist')

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['start_export_url'] = reverse('admin:app_legacyexportjob_start')
        return super().changelist_view(request, extra_context=extra_context)
