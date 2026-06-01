"""Legacy API compatibility layer — drop-in replacement for SaoMiguelBus-webapp."""

from __future__ import annotations

import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from analytics.services import ingest_legacy_stat
from billing.services import verify_subscription
from tenancy.services import for_island
from transit.models import Stop, Trip
from transit.services.ads import get_ad_payload, record_ad_click
from transit.services.compat import serialize_legacy_stops_v2, serialize_webapp_load_v2
from transit.services.gmaps import fetch_directions
from transit.services.search import search_routes

logger = logging.getLogger(__name__)


def _require_island(request: Request):
    if request.island is None:
        return Response({'error': 'Island context required'}, status=400)
    return None


# --- V2 (web PWA primary) ---------------------------------------------------


@api_view(['GET'])
@permission_classes([AllowAny])
def get_all_stops_v2(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err
    with for_island(request.island):
        stops = Stop.objects.all().order_by('name')
        return Response(serialize_legacy_stops_v2(stops))


@api_view(['GET'])
@permission_classes([AllowAny])
def get_webapp_load_v2(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err
    with for_island(request.island):
        return Response(serialize_webapp_load_v2(request.island))


@api_view(['GET'])
@permission_classes([AllowAny])
def get_trip_v2(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err
    with for_island(request.island):
        if request.GET.get('all'):
            trips = Trip.objects.filter(source=Trip.SOURCE_OPERATOR).select_related('line', 'calendar')
            payload = [
                {
                    'id': t.id,
                    'route': t.line.code,
                    'type_of_day': t.calendar.service_type,
                    'likes': t.likes,
                    'dislikes': t.dislikes,
                }
                for t in trips
            ]
            return JsonResponse(payload, safe=False)

        origin = request.GET.get('origin', '')
        destination = request.GET.get('destination', '')
        day = request.GET.get('day', '')
        start = request.GET.get('start', '00:00')
        full = request.GET.get('full', '').lower() == 'true'

        routes = search_routes(
            origin=origin,
            destination=destination,
            day=day,
            start_time=start,
            full=full,
            prefix=True,
        )
        if routes is None:
            return Response({'error': 'Origin and destination are required'}, status=400)
        routes.sort(key=lambda item: item['start'])
        return Response(routes)


@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def like_trip(request: Request, trip_id: int) -> JsonResponse:
    err = _require_island(request)
    if err:
        return JsonResponse({'error': 'Island context required'}, status=400)
    with for_island(request.island):
        try:
            trip = Trip.objects.get(id=trip_id)
        except Trip.DoesNotExist:
            return JsonResponse({'error': 'Trip not found'}, status=404)
        count = int(request.GET.get('count', 1))
        if count == -1:
            trip.likes = max(0, trip.likes - 1)
        elif count == 2:
            trip.dislikes = max(0, trip.dislikes - 1)
            trip.likes += 1
        else:
            trip.likes += 1
        trip.save(update_fields=['likes'])
        total = trip.likes + trip.dislikes
        likes_pct = int(trip.likes / total * 100) if total else 0
        dislikes_pct = int(trip.dislikes / total * 100) if total else 0
        return JsonResponse(
            {
                'message': 'Likes updated successfully',
                'likes_percent': likes_pct,
                'dislikes_percent': dislikes_pct,
            },
            status=200,
        )


@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def dislike_trip(request: Request, trip_id: int) -> JsonResponse:
    err = _require_island(request)
    if err:
        return JsonResponse({'error': 'Island context required'}, status=400)
    with for_island(request.island):
        try:
            trip = Trip.objects.get(id=trip_id)
        except Trip.DoesNotExist:
            return JsonResponse({'error': 'Trip not found'}, status=404)
        count = int(request.GET.get('count', 1))
        if count == -1:
            trip.dislikes = max(0, trip.dislikes - 1)
        elif count == 2:
            trip.likes = max(0, trip.likes - 1)
            trip.dislikes += 1
        else:
            trip.dislikes += 1
        trip.save(update_fields=['dislikes'])
        total = trip.likes + trip.dislikes
        likes_pct = int(trip.likes / total * 100) if total else 0
        dislikes_pct = int(trip.dislikes / total * 100) if total else 0
        return JsonResponse(
            {
                'message': 'Dislikes updated successfully',
                'likes_percent': likes_pct,
                'dislikes_percent': dislikes_pct,
            },
            status=200,
        )


# --- V1 (webapp secondary + desktop) ----------------------------------------


@api_view(['GET'])
@permission_classes([AllowAny])
def get_all_stops_v1(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err
    with for_island(request.island):
        stops = Stop.objects.all().order_by('name')
        return Response(
            [
                {
                    'id': s.id,
                    'name': s.name,
                    'cleaned_name': s.cleaned_name,
                    'latitude': s.latitude,
                    'longitude': s.longitude,
                }
                for s in stops
            ]
        )


@api_view(['GET'])
@permission_classes([AllowAny])
def get_trip_v1(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err
    with for_island(request.island):
        origin = request.GET.get('origin', '')
        destination = request.GET.get('destination', '')
        day = request.GET.get('day', '')
        start = request.GET.get('start', '')
        full = request.GET.get('full', '').lower() == 'true'
        routes = search_routes(
            origin=origin,
            destination=destination,
            day=day,
            start_time=start,
            full=full,
            prefix=False,
        )
        if routes is None:
            return Response(status=404)
        return Response(routes)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_gmaps_v1(request: Request) -> JsonResponse:
    err = _require_island(request)
    if err:
        return JsonResponse({'error': 'Island context required'}, status=400)
    origin = request.GET.get('origin')
    destination = request.GET.get('destination')
    if not (origin and destination):
        return JsonResponse({'error': 'Missing required parameters'}, status=400)
    payload, status_code = fetch_directions(
        island=request.island,
        origin=origin,
        destination=destination,
        language_code=request.GET.get('languageCode', 'en'),
        arrival_departure=request.GET.get('arrival_departure', 'departure'),
        day=request.GET.get('day', ''),
        start=request.GET.get('start', ''),
        time=request.GET.get('time', 'NA'),
        version=request.GET.get('version', '5'),
        auth_key=request.GET.get('key', ''),
    )
    return JsonResponse(payload, status=status_code)


@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def add_stat_v1(request: Request) -> Response:
    ingest_legacy_stat(
        request=request.GET.get('request', 'NA'),
        origin=request.GET.get('origin', ''),
        destination=request.GET.get('destination', ''),
        day=request.GET.get('day', 'NA'),
        time=request.GET.get('time', 'NA'),
        platform=request.GET.get('platform', 'NA'),
        language=request.GET.get('language', 'NA'),
    )
    return Response({'status': 'ok'})


@api_view(['GET'])
@permission_classes([AllowAny])
def get_ad_v1(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err
    with for_island(request.island):
        now = request.GET.get('now')
        now_ts = float(now) if now else None
        payload = get_ad_payload(
            advertise_on=request.GET.get('on', 'all').lower(),
            platform=request.GET.get('platform', 'all'),
            now_ts=now_ts,
        )
        if payload is None:
            return Response(status=404)
        return Response(payload)


@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def click_ad_v1(request: Request) -> Response:
    ad_id = request.GET.get('id', '')
    if not ad_id:
        return Response(status=404)
    if not record_ad_click(int(ad_id)):
        return Response(status=404)
    return Response({'status': 'ok'})


@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def verify_subscription_view(request: Request) -> Response:
    try:
        body = request.data if isinstance(request.data, dict) else json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return Response({'error': 'Invalid JSON'}, status=400)
    email = (body.get('email') or '').strip()
    if not email:
        return Response({'error': 'Invalid request data', 'details': {'email': ['required']}}, status=400)
    result = verify_subscription(
        email=email,
        create_subscription_code=body.get('create_subscription'),
    )
    return Response(result)
