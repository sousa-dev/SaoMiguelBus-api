"""Admin / ops HTTP endpoints (AUTH_KEY protected)."""

from __future__ import annotations

from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from tenancy.celery_control import cancel_all_celery_work


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


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def cancel_all_celery_jobs(request: Request) -> Response:
    """
    Revoke all running Celery tasks, purge the queue, and cancel legacy import jobs.

    Requires AUTH_KEY via ?key= or X-Auth-Key header.
    """
    denied = _require_auth_key(request)
    if denied:
        return denied

    terminate = request.query_params.get('terminate', 'true').lower() not in (
        '0',
        'false',
        'no',
    )
    result = cancel_all_celery_work(terminate_running=terminate)
    return Response(
        {
            'ok': True,
            'message': 'Celery queue purged and running tasks revoked',
            **result,
        }
    )
