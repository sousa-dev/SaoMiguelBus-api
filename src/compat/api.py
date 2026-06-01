"""Legacy API compatibility layer."""

from __future__ import annotations

from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from tenancy.services import for_island
from transit.models import Stop
from transit.services.compat import (
    serialize_legacy_stops_v2,
    serialize_webapp_load_v2,
)


@api_view(['GET'])
def get_all_stops_v2(request: Request) -> Response:
    island = request.island
    if island is None:
        return Response({'error': 'Island context required'}, status=400)
    with for_island(island):
        stops = Stop.objects.all().order_by('name')
        return Response(serialize_legacy_stops_v2(stops))


@api_view(['GET'])
def get_webapp_load_v2(request: Request) -> Response:
    island = request.island
    if island is None:
        return Response({'error': 'Island context required'}, status=400)
    with for_island(island):
        return Response(serialize_webapp_load_v2(island))
