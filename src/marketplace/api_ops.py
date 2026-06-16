"""AUTH_KEY-protected marketplace ops endpoints."""

from __future__ import annotations

from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from marketplace import services
from tenancy.models import Island


def _auth_key_from_request(request: Request) -> str:
    return (
        request.query_params.get('key')
        or request.headers.get('X-Auth-Key')
        or request.headers.get('X-Api-Key')
        or ''
    )


def _require_auth_key(request: Request) -> Response | None:
    if _auth_key_from_request(request) != settings.AUTH_KEY:
        return Response({'error': 'Unauthorized'}, status=401)
    return None


@api_view(['GET'])
@permission_classes([AllowAny])
def fix_provider_phones_view(request: Request) -> Response:
    """
    Normalize provider ``phone`` and ``whatsapp`` values to ``+351XXXXXXXXX``.

    Query params:
      - key / X-Auth-Key: AUTH_KEY (required)
      - island: island key slug, e.g. sao-miguel (optional; all islands if omitted)
      - dry_run: true to preview without saving (default false)
    """
    denied = _require_auth_key(request)
    if denied:
        return denied

    island_key = (request.query_params.get('island') or '').strip()
    dry_run = request.query_params.get('dry_run', 'false').lower() in ('1', 'true', 'yes')
    island = None
    if island_key:
        try:
            island = Island.objects.get(key=island_key)
        except Island.DoesNotExist:
            return Response({'error': f'Unknown island key: {island_key}'}, status=400)

    result = services.fix_provider_phone_numbers(island=island, dry_run=dry_run)
    return Response({'ok': True, **result})
