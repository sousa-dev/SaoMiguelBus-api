"""Seismic v3 API."""

from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from consent.services import hash_session_id
from seismic.models import SeismicEvent
from seismic.serializers import FeltReportSerializer
from seismic.services import get_event, list_events, submit_felt_report
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
def seismic_events_view(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err

    min_mag_raw = request.GET.get('min_magnitude', '').strip()
    min_magnitude = None
    if min_mag_raw:
        try:
            min_magnitude = float(min_mag_raw)
        except ValueError:
            return Response(
                {'error': {'code': 'invalid_min_magnitude', 'message': 'min_magnitude must be a number'}},
                status=status.HTTP_400_BAD_REQUEST,
            )

    limit_raw = request.GET.get('limit', '50').strip()
    try:
        limit = int(limit_raw)
    except ValueError:
        limit = 50

    since_hours_raw = request.GET.get('since_hours', '24').strip()
    since_hours: int | None = 24
    if since_hours_raw:
        try:
            since_hours = int(since_hours_raw)
        except ValueError:
            return Response(
                {
                    'error': {
                        'code': 'invalid_since_hours',
                        'message': 'since_hours must be an integer',
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if since_hours < 0:
            return Response(
                {
                    'error': {
                        'code': 'invalid_since_hours',
                        'message': 'since_hours must be non-negative',
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if since_hours == 0:
            since_hours = None
        else:
            since_hours = min(since_hours, 720)

    with for_island(request.island):
        events = list_events(
            min_magnitude=min_magnitude,
            since_hours=since_hours,
            limit=limit,
        )
    return Response({'events': events})


@api_view(['GET'])
@permission_classes([AllowAny])
def seismic_event_detail_view(request: Request, event_id: int) -> Response:
    err = _require_island(request)
    if err:
        return err

    with for_island(request.island):
        payload = get_event(event_id)
    if payload is None:
        return Response(
            {'error': {'code': 'not_found', 'message': 'Event not found'}},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response(payload)


@api_view(['POST'])
@permission_classes([AllowAny])
def seismic_event_felt_view(request: Request, event_id: int) -> Response:
    err = _require_island(request)
    if err:
        return err

    serializer = FeltReportSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    session_id = data['session_id'].strip()
    if not session_id:
        return Response(
            {'error': {'code': 'session_required', 'message': 'session_id is required'}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    session_hash = hash_session_id(session_id, request.island.key)

    with for_island(request.island):
        if not SeismicEvent.objects.filter(id=event_id).exists():
            return Response(
                {'error': {'code': 'not_found', 'message': 'Event not found'}},
                status=status.HTTP_404_NOT_FOUND,
            )
        payload, created = submit_felt_report(
            event_id=event_id,
            session_hash=session_hash,
            felt=data['felt'],
            intensity=data.get('intensity'),
            latitude=data.get('latitude'),
            longitude=data.get('longitude'),
        )

    return Response(payload, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
