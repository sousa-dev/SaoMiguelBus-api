"""Tenancy v3 API (bootstrap, app update check)."""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from tenancy.bootstrap import serialize_bootstrap
from tenancy.services import for_island
from tenancy.services_release import ReleaseValidationError, build_update_check


@api_view(['GET'])
@permission_classes([AllowAny])
def bootstrap_view(request: Request) -> Response:
    if request.island is None:
        return Response({'error': {'code': 'island_required', 'message': 'Island context required'}}, status=400)
    with for_island(request.island):
        return Response(serialize_bootstrap(request.island))


@api_view(['GET'])
@permission_classes([AllowAny])
def app_update_check_view(request: Request) -> Response:
    if request.island is None:
        return Response({'error': {'code': 'island_required', 'message': 'Island context required'}}, status=400)

    platform = request.query_params.get('platform', '')
    version = request.query_params.get('version', '')

    try:
        payload = build_update_check(platform, version, island=request.island)
    except ReleaseValidationError as exc:
        message = str(exc)
        if 'platform' in message.lower():
            code = 'invalid_platform'
        else:
            code = 'invalid_version'
        return Response({'error': {'code': code, 'message': message}}, status=400)

    return Response(payload)
