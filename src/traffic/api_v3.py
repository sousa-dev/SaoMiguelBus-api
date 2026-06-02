"""Traffic v3 API (function views, service-backed, instant-publish UGC)."""

from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from consent.services import hash_session_id
from tenancy.services import for_island
from traffic import services
from traffic.serializers import ConfirmSerializer, ReportWriteSerializer
from traffic.throttling import TrafficWriteThrottle


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


def _hash_or_empty(session_id: str, request: Request) -> str:
    if not session_id:
        return ''
    return hash_session_id(session_id, request.island.key)


def _float_or_none(raw: str | None) -> float | None:
    if raw is None or str(raw).strip() == '':
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    if not raw:
        return None
    parts = raw.split(',')
    if len(parts) != 4:
        return None
    try:
        min_lng, min_lat, max_lng, max_lat = (float(p) for p in parts)
    except ValueError:
        return None
    return (min_lng, min_lat, max_lng, max_lat)


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
@throttle_classes([TrafficWriteThrottle])
def reports_view(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err

    if request.method == 'GET':
        category = request.GET.get('category', '').strip() or None
        lat = _float_or_none(request.GET.get('lat'))
        lng = _float_or_none(request.GET.get('lng'))
        radius_km = _float_or_none(request.GET.get('radius_km'))
        bbox = _parse_bbox(request.GET.get('bbox'))
        include_scheduled = request.GET.get('include_scheduled', '').lower() in ('1', 'true', 'yes')
        try:
            limit = int(request.GET.get('limit', '100'))
        except ValueError:
            limit = 100
        with for_island(request.island):
            reports = services.list_reports(
                lat=lat, lng=lng, radius_km=radius_km, bbox=bbox,
                category=category, include_scheduled=include_scheduled, limit=limit,
            )
        return Response({'reports': reports})

    serializer = ReportWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    session_id = data['session_id'].strip()
    if not session_id:
        return _error('session_required', 'session_id is required', status.HTTP_400_BAD_REQUEST)
    category_slug = (data.get('category_slug') or '').strip()
    if not category_slug:
        return _error('validation_error', 'category_slug is required', status.HTTP_400_BAD_REQUEST)
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    if latitude is None or longitude is None:
        return _error('validation_error', 'latitude and longitude are required', status.HTTP_400_BAD_REQUEST)

    session_hash = hash_session_id(session_id, request.island.key)
    with for_island(request.island):
        try:
            payload = services.create_report(
                island=request.island,
                session_hash=session_hash,
                category_slug=category_slug,
                latitude=latitude,
                longitude=longitude,
                description=data.get('description', ''),
                road=data.get('road', ''),
                active_from=data.get('active_from'),
                active_until=data.get('active_until'),
            )
        except services.CategoryNotFound:
            return _error('invalid_category', 'Unknown category', status.HTTP_400_BAD_REQUEST)
        except services.SchedulingNotAllowed:
            return _error(
                'scheduling_not_allowed',
                'This category does not support scheduled reports',
                status.HTTP_400_BAD_REQUEST,
            )
        except services.LocationImplausible:
            return _error(
                'location_implausible',
                'Coordinates fall outside the island',
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
    return Response(payload, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([AllowAny])
@throttle_classes([TrafficWriteThrottle])
def report_detail_view(request: Request, report_id: int) -> Response:
    err = _require_island(request)
    if err:
        return err

    is_staff = _is_staff(request)

    if request.method == 'GET':
        with for_island(request.island):
            payload = services.get_report(report_id, is_staff=is_staff)
        if payload is None:
            return _error('not_found', 'Report not found', status.HTTP_404_NOT_FOUND)
        return Response(payload)

    if request.method == 'DELETE':
        session_hash = _hash_or_empty(_session_id(request), request)
        with for_island(request.island):
            try:
                result = services.soft_delete_report(
                    report_id, session_hash=session_hash, is_staff=is_staff
                )
            except services.OwnershipError:
                return _error('not_owner', 'Not allowed', status.HTTP_403_FORBIDDEN)
        if result is None:
            return _error('not_found', 'Report not found', status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)

    # PATCH
    serializer = ReportWriteSerializer(data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    write_session = data.get('session_id', '').strip() or _session_id(request)
    write_hash = _hash_or_empty(write_session, request)
    write_data = {k: v for k, v in data.items() if k != 'session_id'}
    with for_island(request.island):
        try:
            payload = services.update_report(
                report_id, session_hash=write_hash, is_staff=is_staff, data=write_data
            )
        except services.OwnershipError:
            return _error('not_owner', 'Not allowed', status.HTTP_403_FORBIDDEN)
    if payload is None:
        return _error('not_found', 'Report not found', status.HTTP_404_NOT_FOUND)
    return Response(payload)


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([TrafficWriteThrottle])
def report_confirm_view(request: Request, report_id: int) -> Response:
    err = _require_island(request)
    if err:
        return err

    serializer = ConfirmSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    session_id = data['session_id'].strip()
    if not session_id:
        return _error('session_required', 'session_id is required', status.HTTP_400_BAD_REQUEST)
    session_hash = hash_session_id(session_id, request.island.key)
    with for_island(request.island):
        result = services.upsert_confirmation(
            report_id=report_id, session_hash=session_hash, vote=data['vote']
        )
    if result is None:
        return _error('not_found', 'Report not found or inactive', status.HTTP_404_NOT_FOUND)
    payload, created = result
    return Response(payload, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
