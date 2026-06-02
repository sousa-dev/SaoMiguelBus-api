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


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def trigger_feed_sync(request: Request) -> Response:
    """
    Run or queue feed sync tasks (news, seismic, trails) for debugging.

    Query params:
      - key / X-Auth-Key: AUTH_KEY (required)
      - feed: all | news | seismic | trails (default all)
      - island: island key slug, e.g. sao-miguel (optional)
      - async: true to queue on Celery; false to run inline and return counts (default false)
    """
    denied = _require_auth_key(request)
    if denied:
        return denied

    from shared.feed_syncs import FEED_LABELS, normalize_feed_param, trigger_feed_syncs

    feed_param = request.query_params.get('feed', 'all')
    island_key = (request.query_params.get('island') or '').strip() or None
    run_async = request.query_params.get('async', 'false').lower() in ('1', 'true', 'yes')

    try:
        labels = normalize_feed_param(feed_param)
    except ValueError as exc:
        return Response(
            {
                'error': str(exc),
                'allowed_feeds': ['all', *FEED_LABELS],
            },
            status=400,
        )

    results = trigger_feed_syncs(labels, island_key=island_key, run_async=run_async)
    all_ok = all(item.get('ok') for item in results.values())
    return Response(
        {
            'ok': all_ok,
            'island_key': island_key,
            'async': run_async,
            'feeds': results,
        },
        status=200 if all_ok else 502,
    )
