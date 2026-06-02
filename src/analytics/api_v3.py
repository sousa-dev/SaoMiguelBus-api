"""Analytics v3 API."""

from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from analytics.serializers import AnalyticsEventsBatchSerializer
from analytics.services_events import ingest_events
from consent.services import hash_analytics_session_id, hash_session_id
from tenancy.services import for_island


@api_view(['POST'])
@permission_classes([AllowAny])
def analytics_events_view(request: Request) -> Response:
    if request.island is None:
        return Response(
            {'error': {'code': 'island_required', 'message': 'Island context required'}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = AnalyticsEventsBatchSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    consent_session_hash = hash_session_id(data['session_id'], request.island.key)
    analytics_session_hash = hash_analytics_session_id(data['session_id'], request.island.key)

    with for_island(request.island):
        accepted, dropped = ingest_events(
            island=request.island,
            events=data['events'],
            session_hash=analytics_session_hash,
            consent_session_hash=consent_session_hash,
            platform=data.get('platform', 'web'),
            locale=data.get('locale') or request.island.default_locale,
            app_version=data.get('app_version', ''),
        )

    return Response({'accepted': accepted, 'dropped': dropped})
