"""Atlas v3 API — delta-sync and tile-pack discovery for the offline map client."""

from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from atlas.services import SYNC_DEFAULT_LIMIT, build_atlas_stats, build_sync_page
from atlas.throttling import AtlasSyncThrottle
from tenancy.services import for_island


def _require_island(request: Request) -> Response | None:
    if request.island is None:
        return Response(
            {'error': {'code': 'island_required', 'message': 'Island context required'}},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return None


@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([AtlasSyncThrottle])
def stats_view(request: Request) -> Response:
    """Public catalogue totals for the Offline Map landing page (and similar surfaces).

    Island header is optional: omit it for archipelago-wide counts, or send ``X-Island``
    to scope to one tenant.
    """
    if request.island is not None:
        with for_island(request.island):
            payload = build_atlas_stats(island=request.island)
    else:
        payload = build_atlas_stats()
    return Response(payload)


@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([AtlasSyncThrottle])
def sync_view(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err

    try:
        since = int(request.query_params.get('since', '0'))
    except ValueError:
        return Response(
            {'error': {'code': 'invalid_since', 'message': 'since must be an integer'}},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if since < 0:
        return Response(
            {'error': {'code': 'invalid_since', 'message': 'since must be >= 0'}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        limit = int(request.query_params.get('limit', str(SYNC_DEFAULT_LIMIT)))
    except ValueError:
        limit = SYNC_DEFAULT_LIMIT

    with for_island(request.island):
        page = build_sync_page(request.island, since=since, limit=limit)

    from django.utils import timezone

    page['server_time'] = timezone.now().isoformat()

    etag = f'W/"{page["revision"]}"'
    if request.headers.get('If-None-Match') == etag:
        response = Response(status=status.HTTP_304_NOT_MODIFIED)
    else:
        response = Response(page)
    response['ETag'] = etag
    return response
