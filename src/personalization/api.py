"""Personalization v3 API."""

from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from consent.services import hash_session_id
from personalization.serializers import PersonalizationWriteSerializer
from personalization.services import get_latest_profile, save_profile, serialize_profile


def _require_island(request: Request) -> Response | None:
    if request.island is None:
        return Response(
            {'error': {'code': 'island_required', 'message': 'Island context required'}},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return None


def _session_hash(request: Request, session_id: str) -> str:
    return hash_session_id(session_id, request.island.key)


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def personalization_view(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err

    if request.method == 'GET':
        session_id = request.GET.get('session_id', '').strip()
        if not session_id:
            return Response(
                {'error': {'code': 'session_required', 'message': 'session_id is required'}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        session_hash = _session_hash(request, session_id)
        record = get_latest_profile(session_hash=session_hash)
        return Response(serialize_profile(record))

    serializer = PersonalizationWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    session_id = serializer.validated_data['session_id']
    session_hash = _session_hash(request, session_id)
    save_kwargs: dict = {
        'session_hash': session_hash,
        'user_type': serializer.validated_data['user_type'],
        'interests': serializer.validated_data['interests'],
        'home_municipality': serializer.validated_data.get('home_municipality', ''),
        'user': request.user if request.user.is_authenticated else None,
    }
    if 'platform' in serializer.validated_data:
        save_kwargs['platform'] = serializer.validated_data['platform']
    record = save_profile(**save_kwargs)
    return Response(serialize_profile(record), status=status.HTTP_201_CREATED)
