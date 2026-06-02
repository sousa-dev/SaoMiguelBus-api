"""Trails v3 API."""

from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from tenancy.services import for_island
from trails.services import get_trail, list_pois, list_trails


def _require_island(request: Request) -> Response | None:
    if request.island is None:
        return Response(
            {'error': {'code': 'island_required', 'message': 'Island context required'}},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return None


@api_view(['GET'])
@permission_classes([AllowAny])
def trails_list_view(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err

    difficulty = request.GET.get('difficulty', '').strip()
    shape = request.GET.get('shape', '').strip()
    min_length = None
    max_length = None
    min_length_raw = request.GET.get('min_length', '').strip()
    max_length_raw = request.GET.get('max_length', '').strip()
    if min_length_raw:
        try:
            min_length = float(min_length_raw)
        except ValueError:
            return Response(
                {'error': {'code': 'invalid_min_length', 'message': 'min_length must be a number'}},
                status=status.HTTP_400_BAD_REQUEST,
            )
    if max_length_raw:
        try:
            max_length = float(max_length_raw)
        except ValueError:
            return Response(
                {'error': {'code': 'invalid_max_length', 'message': 'max_length must be a number'}},
                status=status.HTTP_400_BAD_REQUEST,
            )

    limit_raw = request.GET.get('limit', '50').strip()
    try:
        limit = int(limit_raw)
    except ValueError:
        limit = 50

    with for_island(request.island):
        payload = list_trails(
            difficulty=difficulty,
            shape=shape,
            min_length=min_length,
            max_length=max_length,
            limit=limit,
        )
    return Response(payload)


@api_view(['GET'])
@permission_classes([AllowAny])
def trails_pois_view(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err

    category = request.GET.get('category', '').strip()
    limit_raw = request.GET.get('limit', '50').strip()
    try:
        limit = int(limit_raw)
    except ValueError:
        limit = 50

    with for_island(request.island):
        payload = list_pois(category=category, limit=limit)
    return Response(payload)


@api_view(['GET'])
@permission_classes([AllowAny])
def trail_detail_view(request: Request, trail_id: int) -> Response:
    err = _require_island(request)
    if err:
        return err

    with for_island(request.island):
        payload = get_trail(trail_id)
    if payload is None:
        return Response(
            {'error': {'code': 'not_found', 'message': 'Trail not found'}},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response(payload)
