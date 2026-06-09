"""Weather v3 API — parish forecasts via Open-Meteo proxy."""

from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from tenancy.services import for_island
from weather.models import Parish
from weather.open_meteo_client import OpenMeteoError
from weather.services import ATTRIBUTION, get_parish_hourly, get_parish_weather, list_parish_weather


def _require_island(request: Request) -> Response | None:
    if request.island is None:
        return Response(
            {'error': {'code': 'island_required', 'message': 'Island context required'}},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return None


@api_view(['GET'])
@permission_classes([AllowAny])
def parishes_list_view(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err

    try:
        with for_island(request.island):
            parishes = list_parish_weather(request.island)
    except OpenMeteoError as exc:
        return Response(
            {'error': {'code': 'weather_unavailable', 'message': str(exc)}},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    return Response({'parishes': parishes, 'attribution': ATTRIBUTION})


@api_view(['GET'])
@permission_classes([AllowAny])
def parish_detail_view(request: Request, slug: str) -> Response:
    err = _require_island(request)
    if err:
        return err

    with for_island(request.island):
        parish = Parish.objects.filter(island=request.island, slug=slug, is_active=True).first()
        if parish is None:
            return Response(
                {'error': {'code': 'not_found', 'message': 'Parish not found'}},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            payload = get_parish_weather(parish)
        except OpenMeteoError as exc:
            return Response(
                {'error': {'code': 'weather_unavailable', 'message': str(exc)}},
                status=status.HTTP_502_BAD_GATEWAY,
            )

    return Response(payload)


@api_view(['GET'])
@permission_classes([AllowAny])
def parish_hourly_view(request: Request, slug: str) -> Response:
    err = _require_island(request)
    if err:
        return err

    date_str = request.query_params.get('date')
    if not date_str:
        return Response(
            {'error': {'code': 'invalid_date', 'message': 'Query parameter date is required (YYYY-MM-DD)'}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    with for_island(request.island):
        parish = Parish.objects.filter(island=request.island, slug=slug, is_active=True).first()
        if parish is None:
            return Response(
                {'error': {'code': 'not_found', 'message': 'Parish not found'}},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            payload = get_parish_hourly(parish, date_str)
        except ValueError as exc:
            return Response(
                {'error': {'code': 'invalid_date', 'message': str(exc)}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except OpenMeteoError as exc:
            return Response(
                {'error': {'code': 'weather_unavailable', 'message': str(exc)}},
                status=status.HTTP_502_BAD_GATEWAY,
            )

    return Response(payload)
