import json

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET

from app.services.legacy_export import build_legacy_export


@require_GET
def export_legacy_data(request):
    """Download full legacy dataset as JSON for revamp ``import_legacy --export-file``."""
    key = request.GET.get('key')
    if key != settings.AUTH_KEY:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    payload = build_legacy_export()
    exported_on = payload['exported_at'][:10]
    filename = f'smb_legacy_export_{exported_on}.json'
    body = json.dumps(payload, indent=2, ensure_ascii=False)

    response = HttpResponse(body, content_type='application/json; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
