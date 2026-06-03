"""Marketplace v3 API (function views, service-backed, session-owned UGC)."""

from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import (
    api_view,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from consent.services import hash_session_id
from marketplace import services
from marketplace.serializers import (
    ModerateSerializer,
    ProviderWriteSerializer,
    ReviewWriteSerializer,
)
from marketplace.throttling import MarketplaceWriteThrottle
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


def _session_id(request: Request) -> str:
    return (
        request.headers.get('X-Session-Id', '').strip()
        or str(request.GET.get('session_id', '')).strip()
    )


def _is_staff(request: Request) -> bool:
    user = getattr(request, 'user', None)
    return bool(user and user.is_authenticated and user.is_staff)


def _write_data(validated: dict) -> dict:
    return {k: v for k, v in validated.items() if k != 'session_id'}


def _validate_provider_write(data: dict, *, require_bio: bool) -> Response | None:
    if require_bio:
        bio = (data.get('bio') or '').strip()
        if not bio:
            return _error('bio_required', 'bio is required', status.HTTP_400_BAD_REQUEST)
    check_contact = require_bio or any(k in data for k in ('phone', 'whatsapp', 'email'))
    if check_contact:
        phone = (data.get('phone') or '').strip()
        whatsapp = (data.get('whatsapp') or '').strip()
        email = (data.get('email') or '').strip()
        if not phone and not whatsapp and not email:
            return _error(
                'contact_required',
                'At least one contact method is required',
                status.HTTP_400_BAD_REQUEST,
            )
    if data.get('claimed_owner'):
        internal_email = (data.get('internal_email') or '').strip()
        internal_phone = (data.get('internal_phone') or '').strip()
        if not internal_email and not internal_phone:
            return _error(
                'owner_contact_required',
                'An owner contact is required when you are the business owner',
                status.HTTP_400_BAD_REQUEST,
            )
    return None


@api_view(['GET'])
@permission_classes([AllowAny])
def categories_view(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err
    with for_island(request.island):
        return Response({'categories': services.list_categories()})


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
@throttle_classes([MarketplaceWriteThrottle])
def providers_view(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err

    if request.method == 'GET':
        category = request.GET.get('category', '').strip() or None
        q = request.GET.get('q', '').strip() or None
        lat = _float_or_none(request.GET.get('lat'))
        lng = _float_or_none(request.GET.get('lng'))
        try:
            limit = int(request.GET.get('limit', '50'))
        except ValueError:
            limit = 50
        with for_island(request.island):
            providers = services.list_providers(
                category=category, q=q, lat=lat, lng=lng, limit=limit
            )
        return Response({'providers': providers})

    serializer = ProviderWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    session_id = data['session_id'].strip()
    if not session_id:
        return _error('session_required', 'session_id is required', status.HTTP_400_BAD_REQUEST)
    name = (data.get('name') or '').strip()
    if not name:
        return _error('validation_error', 'name is required', status.HTTP_400_BAD_REQUEST)

    write_err = _validate_provider_write(data, require_bio=True)
    if write_err:
        return write_err

    session_hash = hash_session_id(session_id, request.island.key)
    with for_island(request.island):
        try:
            payload = services.create_provider(
                island=request.island, session_hash=session_hash, data=_write_data(data)
            )
        except services.CategoryNotFound:
            return _error('invalid_category', 'Unknown category', status.HTTP_400_BAD_REQUEST)
        except services.InvalidCategoryName:
            return _error(
                'invalid_category_name',
                'Invalid category name (2–80 characters, at least one letter)',
                status.HTTP_400_BAD_REQUEST,
            )
    return Response(payload, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([AllowAny])
@throttle_classes([MarketplaceWriteThrottle])
def provider_detail_view(request: Request, provider_id: int) -> Response:
    err = _require_island(request)
    if err:
        return err

    session_hash = _hash_or_empty(_session_id(request), request)
    is_staff = _is_staff(request)

    if request.method == 'GET':
        with for_island(request.island):
            payload = services.get_provider(
                provider_id, viewer_session_hash=session_hash, is_staff=is_staff
            )
        if payload is None:
            return _error('not_found', 'Provider not found', status.HTTP_404_NOT_FOUND)
        return Response(payload)

    if request.method == 'DELETE':
        with for_island(request.island):
            try:
                result = services.soft_delete_provider(
                    provider_id, session_hash=session_hash, is_staff=is_staff
                )
            except services.OwnershipError:
                return _error('not_owner', 'Not allowed', status.HTTP_403_FORBIDDEN)
        if result is None:
            return _error('not_found', 'Provider not found', status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)

    # PUT / PATCH
    serializer = ProviderWriteSerializer(data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    write_err = _validate_provider_write(data, require_bio=False)
    if write_err:
        return write_err
    write_session = data.get('session_id', '').strip() or _session_id(request)
    write_hash = _hash_or_empty(write_session, request)
    with for_island(request.island):
        try:
            payload = services.update_provider(
                provider_id, session_hash=write_hash, is_staff=is_staff, data=_write_data(data)
            )
        except services.OwnershipError:
            return _error('not_owner', 'Not allowed', status.HTTP_403_FORBIDDEN)
        except services.CategoryNotFound:
            return _error('invalid_category', 'Unknown category', status.HTTP_400_BAD_REQUEST)
        except services.InvalidCategoryName:
            return _error(
                'invalid_category_name',
                'Invalid category name (2–80 characters, at least one letter)',
                status.HTTP_400_BAD_REQUEST,
            )
    if payload is None:
        return _error('not_found', 'Provider not found', status.HTTP_404_NOT_FOUND)
    return Response(payload)


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
@throttle_classes([MarketplaceWriteThrottle])
def provider_reviews_view(request: Request, provider_id: int) -> Response:
    err = _require_island(request)
    if err:
        return err

    if request.method == 'GET':
        with for_island(request.island):
            return Response({'reviews': services.list_reviews(provider_id)})

    serializer = ReviewWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    session_id = data['session_id'].strip()
    if not session_id:
        return _error('session_required', 'session_id is required', status.HTTP_400_BAD_REQUEST)
    session_hash = hash_session_id(session_id, request.island.key)
    with for_island(request.island):
        result = services.upsert_review(
            provider_id=provider_id,
            session_hash=session_hash,
            rating=data['rating'],
            text=data.get('text', ''),
        )
    if result is None:
        return _error('not_found', 'Provider not found', status.HTTP_404_NOT_FOUND)
    payload, created = result
    return Response(payload, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@api_view(['PUT', 'PATCH', 'DELETE'])
@permission_classes([AllowAny])
@throttle_classes([MarketplaceWriteThrottle])
def review_detail_view(request: Request, review_id: int) -> Response:
    err = _require_island(request)
    if err:
        return err

    is_staff = _is_staff(request)

    if request.method == 'DELETE':
        session_hash = _hash_or_empty(_session_id(request), request)
        with for_island(request.island):
            try:
                result = services.delete_review(
                    review_id, session_hash=session_hash, is_staff=is_staff
                )
            except services.OwnershipError:
                return _error('not_owner', 'Not allowed', status.HTTP_403_FORBIDDEN)
        if result is None:
            return _error('not_found', 'Review not found', status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = ReviewWriteSerializer(data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    session_hash = _hash_or_empty(
        data.get('session_id', '').strip() or _session_id(request), request
    )
    with for_island(request.island):
        try:
            payload = services.update_review(
                review_id, session_hash=session_hash, is_staff=is_staff, data=_write_data(data)
            )
        except services.OwnershipError:
            return _error('not_owner', 'Not allowed', status.HTTP_403_FORBIDDEN)
    if payload is None:
        return _error('not_found', 'Review not found', status.HTTP_404_NOT_FOUND)
    return Response(payload)


@api_view(['POST'])
@permission_classes([AllowAny])
def provider_moderate_view(request: Request, provider_id: int) -> Response:
    err = _require_island(request)
    if err:
        return err
    if not _is_staff(request):
        return _error('not_authorized', 'Staff only', status.HTTP_403_FORBIDDEN)
    serializer = ModerateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    with for_island(request.island):
        payload = services.moderate_provider(provider_id, serializer.validated_data['action'])
    if payload is None:
        return _error('not_found', 'Provider not found', status.HTTP_404_NOT_FOUND)
    return Response(payload)


@api_view(['POST'])
@permission_classes([AllowAny])
def review_moderate_view(request: Request, review_id: int) -> Response:
    err = _require_island(request)
    if err:
        return err
    if not _is_staff(request):
        return _error('not_authorized', 'Staff only', status.HTTP_403_FORBIDDEN)
    serializer = ModerateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    with for_island(request.island):
        payload = services.moderate_review(review_id, serializer.validated_data['action'])
    if payload is None:
        return _error('not_found', 'Review not found', status.HTTP_404_NOT_FOUND)
    return Response(payload)


def _float_or_none(raw: str | None) -> float | None:
    if raw is None or str(raw).strip() == '':
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _hash_or_empty(session_id: str, request: Request) -> str:
    if not session_id:
        return ''
    return hash_session_id(session_id, request.island.key)
