"""Marketplace superuser admin API (moderation queues and edits)."""

from __future__ import annotations

from functools import wraps

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from marketplace import services
from marketplace.models import Review, ServiceProvider
from marketplace.permissions import is_marketplace_superuser
from marketplace.serializers import (
    CategoryAdminWriteSerializer,
    ModerateSerializer,
    ProviderAdminWriteSerializer,
    ReviewAdminWriteSerializer,
)
from tenancy.services import for_island


def _require_island(request: Request) -> Response | None:
    if request.island is None:
        return Response(
            {'error': {'code': 'island_required', 'message': 'Island context required'}},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return None


def _error(code: str, message: str, http_status: int) -> Response:
    return Response({'error': {'code': code, 'message': message}}, status=http_status)


def superuser_required(view_func):
    @wraps(view_func)
    def wrapper(request: Request, *args, **kwargs):
        if not is_marketplace_superuser(request):
            return _error('not_authorized', 'Superuser only', status.HTTP_403_FORBIDDEN)
        return view_func(request, *args, **kwargs)

    return wrapper


def _int_param(raw: str | None, default: int) -> int:
    if raw is None or str(raw).strip() == '':
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@superuser_required
def admin_queue_view(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err
    with for_island(request.island):
        return Response(services.admin_queue_summary())


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@superuser_required
def admin_providers_view(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err
    status_filter = request.GET.get('status', ServiceProvider.PENDING).strip() or None
    limit = _int_param(request.GET.get('limit'), services.DEFAULT_LIMIT)
    offset = _int_param(request.GET.get('offset'), 0)
    with for_island(request.island):
        return Response(
            services.list_admin_providers(status=status_filter, limit=limit, offset=offset)
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@superuser_required
def admin_reviews_view(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err
    status_filter = request.GET.get('status', Review.PENDING).strip() or None
    limit = _int_param(request.GET.get('limit'), services.DEFAULT_LIMIT)
    offset = _int_param(request.GET.get('offset'), 0)
    with for_island(request.island):
        return Response(
            services.list_admin_reviews(status=status_filter, limit=limit, offset=offset)
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@superuser_required
def admin_categories_view(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err
    suggested = request.GET.get('suggested', '1').strip().lower() not in {'0', 'false', 'no'}
    with for_island(request.island):
        return Response({'categories': services.list_admin_categories(suggested_only=suggested)})


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
@superuser_required
def admin_provider_detail_view(request: Request, provider_id: int) -> Response:
    err = _require_island(request)
    if err:
        return err
    serializer = ProviderAdminWriteSerializer(data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    with for_island(request.island):
        payload = services.update_provider_admin(provider_id, serializer.validated_data)
    if payload is None:
        return _error('not_found', 'Provider not found', status.HTTP_404_NOT_FOUND)
    return Response(payload)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
@superuser_required
def admin_review_detail_view(request: Request, review_id: int) -> Response:
    err = _require_island(request)
    if err:
        return err
    serializer = ReviewAdminWriteSerializer(data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    with for_island(request.island):
        payload = services.update_review_admin(review_id, serializer.validated_data)
    if payload is None:
        return _error('not_found', 'Review not found', status.HTTP_404_NOT_FOUND)
    return Response(payload)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
@superuser_required
def admin_category_detail_view(request: Request, category_id: int) -> Response:
    err = _require_island(request)
    if err:
        return err
    serializer = CategoryAdminWriteSerializer(data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    approve = bool(data.pop('approve', False))
    with for_island(request.island):
        try:
            payload = services.update_category_admin(category_id, data, approve=approve)
        except services.CategorySlugConflict:
            return _error(
                'slug_conflict',
                'Category slug already in use',
                status.HTTP_400_BAD_REQUEST,
            )
    if payload is None:
        return _error('not_found', 'Category not found', status.HTTP_404_NOT_FOUND)
    return Response(payload)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@superuser_required
def admin_provider_moderate_view(request: Request, provider_id: int) -> Response:
    err = _require_island(request)
    if err:
        return err
    serializer = ModerateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    with for_island(request.island):
        payload = services.moderate_provider(provider_id, serializer.validated_data['action'])
    if payload is None:
        return _error('not_found', 'Provider not found', status.HTTP_404_NOT_FOUND)
    return Response(payload)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@superuser_required
def admin_review_moderate_view(request: Request, review_id: int) -> Response:
    err = _require_island(request)
    if err:
        return err
    serializer = ModerateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    with for_island(request.island):
        payload = services.moderate_review(review_id, serializer.validated_data['action'])
    if payload is None:
        return _error('not_found', 'Review not found', status.HTTP_404_NOT_FOUND)
    return Response(payload)
