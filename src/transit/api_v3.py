"""Transit v3 API."""

from __future__ import annotations

from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from tenancy.services import for_island
from transit.models import Trip
from transit.services.directions_v3 import get_directions_v3
from transit.services.offline_bundle import compute_bundle_version, get_offline_bundle_cached
from transit.services.route_weather import get_route_weather
from transit.services.v3 import (
    get_line_v3,
    get_trip_v3,
    search_transit_v3,
    serialize_stops_v3,
    serialize_trip_detail,
)
from transit.throttling import DirectionsSessionThrottle, OfflineBundleThrottle
from weather.open_meteo_client import OpenMeteoError


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
        from transit.models import Stop
        from transit.services.schedule_phase import resolve_dataset

        dataset = resolve_dataset(
            request.island, requested=request.GET.get('dataset'),
        )
        stops = Stop.objects.filter(dataset=dataset).order_by('name')
        return Response({'stops': serialize_stops_v3(stops)})


@api_view(['GET'])
@permission_classes([AllowAny])
def transit_offline_version_view(request: Request) -> Response:
    """Lightweight staleness probe — client polls this before downloading."""
    err = _require_island(request)
    if err:
        return err
    with for_island(request.island):
        version = compute_bundle_version(request.island)
    return Response({'version': version, 'island': request.island.key})


@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([OfflineBundleThrottle])
def transit_offline_bundle_view(request: Request) -> Response:
    """Self-contained transit dataset for offline route search.

    Supports conditional GET via ETag (secondary to the /version poll): a client
    that sends a matching If-None-Match gets 304 without the payload.
    """
    err = _require_island(request)
    if err:
        return err

    with for_island(request.island):
        version = compute_bundle_version(request.island)
        if_none_match = request.headers.get('If-None-Match', '').strip().strip('"')
        if if_none_match and if_none_match == version:
            not_modified = Response(status=status.HTTP_304_NOT_MODIFIED)
            not_modified['ETag'] = f'"{version}"'
            return not_modified

        bundle = get_offline_bundle_cached(request.island)

    response = Response(bundle)
    response['ETag'] = f'"{bundle["version"]}"'
    response['Cache-Control'] = 'no-cache'
    return response


@api_view(['GET'])
@permission_classes([AllowAny])
def transit_tariffs_view(request: Request) -> Response:
    """Fare TABLES. Never a per-ride price -- see services_tariffs."""
    err = _require_island(request)
    if err:
        return err

    from azoresbus.services_tariffs import current_snapshot, serialize_tariffs

    with for_island(request.island):
        snapshot = current_snapshot(request.island)
        if snapshot is None:
            return Response(
                {'error': {'code': 'not_found',
                           'message': 'No tariff snapshot has been synced yet'}},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(serialize_tariffs(snapshot))


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
        from transit.services.schedule_phase import resolve_dataset

        results = search_transit_v3(
            origin=origin,
            destination=destination,
            day=day,
            start_time=start,
            dataset=resolve_dataset(
                request.island, requested=request.GET.get('dataset'),
            ),
        )
        if results is None:
            return Response(
                {'error': {'code': 'invalid_params', 'message': 'origin and destination are required'}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({'results': results})


@api_view(['GET'])
@permission_classes([AllowAny])
def transit_route_weather_view(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err

    origin = request.GET.get('origin', '').strip()
    destination = request.GET.get('destination', '').strip()
    if not origin or not destination:
        return Response(
            {'error': {'code': 'invalid_params', 'message': 'origin and destination are required'}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    origin_at_raw = request.GET.get('origin_at', '').strip()
    destination_at_raw = request.GET.get('destination_at', '').strip()
    origin_at = parse_datetime(origin_at_raw) if origin_at_raw else None
    destination_at = parse_datetime(destination_at_raw) if destination_at_raw else None

    try:
        with for_island(request.island):
            payload = get_route_weather(
                island=request.island,
                origin=origin,
                destination=destination,
                origin_at=origin_at,
                destination_at=destination_at,
            )
    except OpenMeteoError as exc:
        return Response(
            {'error': {'code': 'weather_unavailable', 'message': str(exc)}},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    return Response(payload)


@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([DirectionsSessionThrottle])
def transit_directions_view(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err

    origin = request.GET.get('origin', '').strip()
    destination = request.GET.get('destination', '').strip()
    if not origin or not destination:
        return Response(
            {'error': {'code': 'invalid_params', 'message': 'origin and destination are required'}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    locale = request.GET.get('locale') or request.GET.get('languageCode') or 'pt'
    with for_island(request.island):
        payload, status_code, from_cache = get_directions_v3(
            island=request.island,
            origin=origin,
            destination=destination,
            language_code=locale,
            arrival_departure=request.GET.get('arrival_departure', 'departure'),
            day=request.GET.get('day', ''),
            start=request.GET.get('start', ''),
            date=request.GET.get('date', ''),
        )

    if status_code == 400 and isinstance(payload.get('error'), str):
        return Response(
            {'error': {'code': 'maps_disabled', 'message': payload['error']}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    response = Response(payload, status=status_code)
    if from_cache:
        response['X-Directions-Cache'] = 'hit'
    return response


@api_view(['GET'])
@permission_classes([AllowAny])
def transit_trip_detail_view(request: Request, trip_id: int) -> Response:
    err = _require_island(request)
    if err:
        return err

    with for_island(request.island):
        payload = get_trip_v3(trip_id)
        if payload is None:
            return Response(
                {'error': {'code': 'not_found', 'message': 'Trip not found'}},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(payload)


@api_view(['GET'])
@permission_classes([AllowAny])
def transit_line_detail_view(request: Request, line_code: str) -> Response:
    err = _require_island(request)
    if err:
        return err

    with for_island(request.island):
        payload = get_line_v3(line_code)
        if payload is None:
            return Response(
                {'error': {'code': 'not_found', 'message': 'Line not found'}},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(payload)


@api_view(['POST'])
@permission_classes([AllowAny])
def transit_trip_vote_view(request: Request, trip_id: int) -> Response:
    err = _require_island(request)
    if err:
        return err

    from transit.services.schedule_phase import resolve_dataset

    vote = (request.data.get('vote') or request.GET.get('vote') or 'like').lower()

    with for_island(request.island):
        try:
            # PKs do not collide across datasets today, but a vote is a write:
            # filter for defence (02 section 7.0).
            trip = Trip.objects.filter(
                dataset=resolve_dataset(request.island)
            ).get(id=trip_id)
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
