"""Events v3 API — Viator tours proxy."""

from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from events.services import get_tour, list_tours
from events.viator_client import ViatorError, ViatorNotConfigured
from tenancy.services import for_island


def _require_island(request: Request) -> Response | None:
    if request.island is None:
        return Response(
            {'error': {'code': 'island_required', 'message': 'Island context required'}},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return None


def _resolve_locale(request: Request) -> str:
    query = request.GET.get('locale', '').strip()
    if query:
        return query
    header = request.headers.get('Accept-Language') or request.META.get('HTTP_ACCEPT_LANGUAGE') or ''
    if header:
        return header.split(',')[0].strip()
    return 'en'


@api_view(['GET'])
@permission_classes([AllowAny])
def tours_list_view(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err

    locale = _resolve_locale(request)
    currency = request.GET.get('currency', 'EUR').strip() or 'EUR'
    sort = request.GET.get('sort', 'DEFAULT').strip() or 'DEFAULT'
    limit_raw = request.GET.get('limit', request.GET.get('count', '30')).strip()
    try:
        count = min(max(int(limit_raw), 1), 50)
    except ValueError:
        count = 30
    start_raw = request.GET.get('start', '1').strip()
    try:
        start = max(int(start_raw), 1)
    except ValueError:
        start = 1

    try:
        with for_island(request.island):
            tours = list_tours(
                locale=locale,
                currency=currency,
                sort=sort,
                start=start,
                count=count,
            )
    except ViatorNotConfigured:
        return Response(
            {'error': {'code': 'viator_unavailable', 'message': 'Tours provider not configured'}},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    except ViatorError as exc:
        return Response(
            {'error': {'code': 'viator_unavailable', 'message': str(exc)}},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    return Response({'tours': tours})


@api_view(['GET'])
@permission_classes([AllowAny])
def tour_detail_view(request: Request, product_code: str) -> Response:
    err = _require_island(request)
    if err:
        return err

    locale = _resolve_locale(request)
    currency = request.GET.get('currency', 'EUR').strip() or 'EUR'

    try:
        with for_island(request.island):
            tour = get_tour(product_code, locale=locale, currency=currency)
    except ViatorNotConfigured:
        return Response(
            {'error': {'code': 'viator_unavailable', 'message': 'Tours provider not configured'}},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    except ViatorError as exc:
        return Response(
            {'error': {'code': 'viator_unavailable', 'message': str(exc)}},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    if tour is None:
        return Response(
            {'error': {'code': 'not_found', 'message': 'Tour not found'}},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response(tour)
