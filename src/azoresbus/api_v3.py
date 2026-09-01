"""AzoresBus tracking endpoints.

Shipped dark originally (02 §8, 98 §5 challenge 6); the fleet reports live as of
September 2026 and `trackingEnabled` gates whether clients can see it.

Three states the client distinguishes, so none of these statuses may be
casually changed:

    503 tracking_disabled     the flag is off -- the feature does not exist
    502 tracking_unavailable  the AVL is down -- try again shortly
    200 {"vehicles": [...]}   including `[]`, which means nobody is reporting
"""

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

from azoresbus.services_arrivals import stop_arrivals
from azoresbus.services_route_index import route_catalogue
from azoresbus.services_tracking import (
    TrackingDisabled,
    get_fleet,
    get_tracking_health,
    get_vehicle,
)
from azoresbus.throttling import AzoresbusTrackingThrottle
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
@throttle_classes([AzoresbusTrackingThrottle])
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
@throttle_classes([AzoresbusTrackingThrottle])
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
@throttle_classes([AzoresbusTrackingThrottle])
def azoresbus_tracking_health_view(request: Request) -> Response:
    """Availability probe. Distinguishes disabled from empty from broken."""
    err = _require_island(request)
    if err:
        return err
    force = request.GET.get('force') in ('1', 'true')
    with for_island(request.island):
        try:
            return Response(get_tracking_health(request.island, force=force))
        except AzoresbusTrackingError:
            return Response({'status': 'unavailable', 'vehicles': 0},
                            status=status.HTTP_502_BAD_GATEWAY)


@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([AzoresbusTrackingThrottle])
def azoresbus_routes_view(request: Request) -> Response:
    """The route catalogue, for naming and colouring line filters.

    Not gated on `trackingEnabled`: this is static network reference data, and a
    503 here would be a lie about the network rather than about tracking. An
    upstream failure degrades to an empty list rather than an error, because a
    map with unnamed lines still works.
    """
    err = _require_island(request)
    if err:
        return err
    with for_island(request.island):
        routes = route_catalogue(request.island)
    return Response({'routes': sorted(
        routes.values(), key=lambda route: route['nameShort'],
    )})


@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([AzoresbusTrackingThrottle])
def azoresbus_stop_arrivals_view(request: Request, stop_id: int) -> Response:
    """Live buses inbound to one of our stops.

    An empty list is a real answer -- at 23:00 nothing is running -- and is
    deliberately distinct from the 503 you get when tracking is switched off and
    the 502 when the AVL is unreachable. The client renders three different
    things for those.
    """
    err = _require_island(request)
    if err:
        return err
    with for_island(request.island):
        try:
            return Response({'arrivals': stop_arrivals(request.island, stop_id)})
        except TrackingDisabled:
            return _disabled()
        except AzoresbusTrackingError:
            return Response(
                {'error': {'code': 'tracking_unavailable',
                           'message': 'Upstream AVL unavailable'}},
                status=status.HTTP_502_BAD_GATEWAY,
            )
