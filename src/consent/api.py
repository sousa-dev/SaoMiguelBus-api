"""Consent v3 API."""

from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from consent.serializers import ConsentWriteSerializer
from consent.services import (
    CONSENT_POLICY_VERSION,
    get_latest_consent,
    hash_session_id,
    save_consent,
    serialize_consent,
)


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
def consent_view(request: Request) -> Response:
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
        record = get_latest_consent(session_hash=session_hash)
        return Response(serialize_consent(record))

    serializer = ConsentWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    session_id = serializer.validated_data['session_id']
    session_hash = _session_hash(request, session_id)
    record = save_consent(
        session_hash=session_hash,
        purposes=serializer.validated_data['purposes'],
        policy_version=serializer.validated_data.get('policy_version'),
        user=request.user if request.user.is_authenticated else None,
    )
    payload = serialize_consent(record)
    payload['policy_version'] = record.policy_version or CONSENT_POLICY_VERSION
    return Response(payload, status=status.HTTP_201_CREATED)
