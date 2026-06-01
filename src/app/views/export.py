from django.conf import settings
from django.http import FileResponse, JsonResponse
from django.views.decorators.http import require_GET

from app.models import LegacyExportJob
from app.services.legacy_export import get_job, read_job_status, start_legacy_export_job


def _check_auth(request):
    key = request.GET.get('key')
    if key != settings.AUTH_KEY:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    return None


def _status_urls(request, job_id: str) -> dict[str, str]:
    base = request.build_absolute_uri('/api/v1/export/legacy').split('?')[0]
    key = request.GET.get('key', '')
    query = f'key={key}&job_id={job_id}'
    return {
        'status_url': f'{base}/status?{query}',
        'download_url': f'{base}/download?{query}',
    }


@require_GET
def export_legacy_data(request):
    """Start a background legacy export job (returns immediately)."""
    auth_error = _check_auth(request)
    if auth_error:
        return auth_error

    status = start_legacy_export_job()
    job_id = status['job_id']
    urls = _status_urls(request, job_id)
    return JsonResponse(
        {
            'message': 'Export started in background',
            'job_id': job_id,
            'status': status.get('status'),
            'started_at': status.get('started_at'),
            **urls,
        },
        status=202,
    )


@require_GET
def export_legacy_status(request):
    """Poll export job status."""
    auth_error = _check_auth(request)
    if auth_error:
        return auth_error

    job_id = request.GET.get('job_id')
    if not job_id:
        return JsonResponse({'error': 'job_id is required'}, status=400)

    status = read_job_status(job_id)
    if status is None:
        return JsonResponse({'error': 'Unknown job_id'}, status=404)

    urls = _status_urls(request, job_id)
    return JsonResponse({**status, **urls})


@require_GET
def export_legacy_download(request):
    """Download completed export file."""
    auth_error = _check_auth(request)
    if auth_error:
        return auth_error

    job_id = request.GET.get('job_id')
    if not job_id:
        return JsonResponse({'error': 'job_id is required'}, status=400)

    job = get_job(job_id)
    if job is None:
        return JsonResponse({'error': 'Unknown job_id'}, status=404)
    if job.status != LegacyExportJob.STATUS_COMPLETED:
        return JsonResponse(
            {
                'error': 'Export not ready',
                'status': job.status,
                'job_id': job_id,
            },
            status=409,
        )
    if not job.export_file:
        return JsonResponse({'error': 'Export file missing on disk'}, status=500)

    exported_on = (job.exported_at or job.finished_at or job.started_at).strftime('%Y-%m-%d')
    filename = f'smb_legacy_export_{exported_on}.json'
    return FileResponse(
        job.export_file.open('rb'),
        as_attachment=True,
        filename=filename,
        content_type='application/json; charset=utf-8',
    )
