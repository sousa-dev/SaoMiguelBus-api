"""Tenancy v3 API (bootstrap)."""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from tenancy.bootstrap import serialize_bootstrap
from tenancy.services import for_island


@api_view(['GET'])
@permission_classes([AllowAny])
def bootstrap_view(request: Request) -> Response:
    if request.island is None:
        return Response({'error': {'code': 'island_required', 'message': 'Island context required'}}, status=400)
    with for_island(request.island):
        return Response(serialize_bootstrap(request.island))
