"""Transit v3 API."""

from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from tenancy.services import for_island
from transit.models import Stop, Trip
from transit.services.v3 import (
    search_transit_v3,
    serialize_stops_v3,
    serialize_trip_detail,
)


def _require_island(request: Request) -> Response | None:
    if request.island is None:
        return Response(
            {'error': {'code': 'island_required', 'message': 'Island context required'}},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return None


@api_view(['GET'])
@permission_classes([AllowAny])
def transit_stops_view(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err
    with for_island(request.island):
        stops = Stop.objects.all().order_by('name')
        return Response({'stops': serialize_stops_v3(stops)})


@api_view(['GET'])
@permission_classes([AllowAny])
def transit_search_view(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err

    origin = request.GET.get('origin', '').strip()
    destination = request.GET.get('destination', '').strip()
    day = request.GET.get('day', 'weekday')
    start = request.GET.get('start', '00:00')

    if not origin or not destination:
        return Response(
            {'error': {'code': 'invalid_params', 'message': 'origin and destination are required'}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    with for_island(request.island):
        results = search_transit_v3(
            origin=origin,
            destination=destination,
            day=day,
            start_time=start,
        )
        if results is None:
            return Response(
                {'error': {'code': 'invalid_params', 'message': 'origin and destination are required'}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({'results': results})


@api_view(['POST'])
@permission_classes([AllowAny])
def transit_trip_vote_view(request: Request, trip_id: int) -> Response:
    err = _require_island(request)
    if err:
        return err

    vote = (request.data.get('vote') or request.GET.get('vote') or 'like').lower()

    with for_island(request.island):
        try:
            trip = Trip.objects.get(id=trip_id)
        except Trip.DoesNotExist:
            return Response(
                {'error': {'code': 'not_found', 'message': 'Trip not found'}},
                status=status.HTTP_404_NOT_FOUND,
            )

        if vote == 'dislike':
            trip.dislikes += 1
            trip.save(update_fields=['dislikes'])
        elif vote == 'undo_like':
            trip.likes = max(0, trip.likes - 1)
            trip.save(update_fields=['likes'])
        elif vote == 'undo_dislike':
            trip.dislikes = max(0, trip.dislikes - 1)
            trip.save(update_fields=['dislikes'])
        elif vote == 'switch_to_like':
            trip.dislikes = max(0, trip.dislikes - 1)
            trip.likes += 1
            trip.save(update_fields=['likes', 'dislikes'])
        else:
            trip.likes += 1
            trip.save(update_fields=['likes'])

        total = trip.likes + trip.dislikes
        likes_pct = int(trip.likes / total * 100) if total else 0
        dislikes_pct = int(trip.dislikes / total * 100) if total else 0

        payload = serialize_trip_detail(trip)
        payload['likesPercent'] = likes_pct
        payload['dislikesPercent'] = dislikes_pct
        return Response(payload)
