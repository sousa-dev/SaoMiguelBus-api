"""AzoresBus tracking endpoints. Shipped dark (02 §8, 98 §5 challenge 6).

The fleet is `[]` today. The client, cache layer, endpoints and flag ship now;
the map UI waits until /api/locations is non-empty or preview has shipped.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from azoresbus.services_tracking import (
    TrackingDisabled,
    get_fleet,
    get_vehicle,
    tracking_enabled,
)
from azoresbus.tracking_client import (
    AzoresbusTrackingError,
    AzoresbusVehicleNotFound,
)
from tenancy.services import for_island


def _require_island(request: Request):
    if getattr(request, 'island', None) is None:
        return Response(
            {'error': {'code': 'island_required', 'message': 'Island required'}},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return None


def _disabled() -> Response:
    return Response(
        {'error': {'code': 'tracking_disabled',
                   'message': 'Live tracking is not enabled'}},
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


@api_view(['GET'])
@permission_classes([AllowAny])
def azoresbus_vehicles_view(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err
    with for_island(request.island):
        try:
            return Response({'vehicles': get_fleet(request.island)})
        except TrackingDisabled:
            return _disabled()
        except AzoresbusTrackingError:
            return Response(
                {'error': {'code': 'tracking_unavailable',
                           'message': 'Upstream AVL unavailable'}},
                status=status.HTTP_502_BAD_GATEWAY,
            )


@api_view(['GET'])
@permission_classes([AllowAny])
def azoresbus_vehicle_detail_view(request: Request, vehicle_id: str) -> Response:
    err = _require_island(request)
    if err:
        return err
    with for_island(request.island):
        try:
            return Response(get_vehicle(request.island, vehicle_id))
        except TrackingDisabled:
            return _disabled()
        except AzoresbusVehicleNotFound:
            return Response(
                {'error': {'code': 'not_found', 'message': 'Vehicle not found'}},
                status=status.HTTP_404_NOT_FOUND,
            )
        except AzoresbusTrackingError:
            return Response(
                {'error': {'code': 'tracking_unavailable',
                           'message': 'Upstream AVL unavailable'}},
                status=status.HTTP_502_BAD_GATEWAY,
            )


@api_view(['GET'])
@permission_classes([AllowAny])
def azoresbus_tracking_health_view(request: Request) -> Response:
    """Availability probe. Distinguishes disabled from empty from broken."""
    err = _require_island(request)
    if err:
        return err
    with for_island(request.island):
        if not tracking_enabled(request.island):
            return Response({'status': 'disabled', 'vehicles': 0})
        try:
            fleet = get_fleet(request.island)
        except AzoresbusTrackingError:
            return Response({'status': 'unavailable', 'vehicles': 0},
                            status=status.HTTP_502_BAD_GATEWAY)
        return Response({'status': 'ok', 'vehicles': len(fleet)})
