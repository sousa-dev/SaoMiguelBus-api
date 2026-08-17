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
    search_journeys_v3,
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
def transit_offline_bundle_v2_view(request: Request) -> Response:
    """Schema-versioned bundle. Only new builds request it (00 Decision 4)."""
    err = _require_island(request)
    if err:
        return err
    with for_island(request.island):
        from transit.services.offline_bundle_v2 import build_offline_bundle_v2

        return Response(build_offline_bundle_v2(request.island))


@api_view(['GET'])
@permission_classes([AllowAny])
def transit_offline_bundle_v2_version_view(request: Request) -> Response:
    """Fingerprint only, for the staleness probe."""
    err = _require_island(request)
    if err:
        return err
    with for_island(request.island):
        from transit.services.offline_bundle_v2 import compute_version_v2

        return Response({'version': compute_version_v2(request.island)})


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
def transit_line_shape_view(request: Request, line_code: str) -> Response:
    """A whole line drawn end to end: one path and stop list per direction."""
    err = _require_island(request)
    if err:
        return err

    with for_island(request.island):
        from transit.models import Line
        from transit.services.geometry import line_shapes, line_stops
        from transit.services.schedule_phase import resolve_dataset

        dataset = resolve_dataset(
            request.island, requested=request.GET.get('dataset'),
        )
        try:
            line = Line.objects.get(dataset=dataset, code=line_code)
        except Line.DoesNotExist:
            return Response(
                {'error': {'code': 'not_found', 'message': 'Line not found'}},
                status=status.HTTP_404_NOT_FOUND,
            )

        shapes = line_shapes(line)
        directions = line_stops(line)
        by_direction = {entry['direction']: entry for entry in directions}

        return Response({
            'code': line.code,
            'displayName': line.display_name,
            'directions': [
                {
                    'direction': shape['direction'],
                    'shape': shape['shape'],
                    'tripId': shape['tripId'],
                    'stops': by_direction.get(shape['direction'], {}).get('stops', []),
                }
                for shape in shapes
            ],
        })


@api_view(['GET'])
@permission_classes([AllowAny])
def transit_stop_detail_view(request: Request, stop_id: int) -> Response:
    """One stop: where its poles physically are, what serves it, what is next.

    `day`/`start` default to the same shapes `/search` accepts, so the
    departures a rider sees here obey exactly the service rules that decide
    whether a journey is plannable.
    """
    err = _require_island(request)
    if err:
        return err

    with for_island(request.island):
        from transit.models import Stop
        from transit.services.schedule_phase import resolve_dataset
        from transit.services.stops import serialize_stop_detail

        dataset = resolve_dataset(
            request.island, requested=request.GET.get('dataset'),
        )
        try:
            stop = (
                Stop.objects.filter(dataset=dataset)
                .prefetch_related('external_stops')
                .get(id=stop_id)
            )
        except Stop.DoesNotExist:
            return Response(
                {'error': {'code': 'not_found', 'message': 'Stop not found'}},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(serialize_stop_detail(
            stop,
            day=request.GET.get('day', 'weekday'),
            start_time=request.GET.get('start', '00:00'),
        ))


@api_view(['GET'])
@permission_classes([AllowAny])
def transit_trip_geometry_view(request: Request, trip_id: int) -> Response:
    """The path and stop positions for one ride, for drawing a map.

    Deliberately NOT folded into `/journeys`. A 20-journey response would grow by
    tens of kilobytes of polyline for maps that mostly never get opened, so the
    map fetches per ride leg and the client caches it — the same split `trails`
    already makes between its list and detail views.

    `from`/`to` are the `board.sequence` / `alight.sequence` the journey response
    already carries. Omit them for the whole trip.
    """
    err = _require_island(request)
    if err:
        return err

    with for_island(request.island):
        from transit.models import Trip
        from transit.services.geometry import leg_geometry
        from transit.services.schedule_phase import resolve_dataset

        dataset = resolve_dataset(
            request.island, requested=request.GET.get('dataset'),
        )
        try:
            trip = (
                Trip.objects.filter(dataset=dataset)
                .select_related('line')
                .prefetch_related('stop_times__stop', 'stop_times__external_stop')
                .get(id=trip_id)
            )
        except Trip.DoesNotExist:
            return Response(
                {'error': {'code': 'not_found', 'message': 'Trip not found'}},
                status=status.HTTP_404_NOT_FOUND,
            )

        stop_times = sorted(trip.stop_times.all(), key=lambda st: st.sequence)
        if not stop_times:
            return Response(
                {'error': {'code': 'not_found', 'message': 'Trip has no stops'}},
                status=status.HTTP_404_NOT_FOUND,
            )

        board = _stop_time_at(stop_times, request.GET.get('from')) or stop_times[0]
        alight = _stop_time_at(stop_times, request.GET.get('to')) or stop_times[-1]
        if board.sequence > alight.sequence:
            board, alight = alight, board

        return Response(leg_geometry(trip, board, alight))


def _stop_time_at(stop_times, raw: str | None):
    """Resolve a `sequence` query param, tolerating junk.

    A bad index is a client bug, not a reason to fail a map: falling back to the
    whole trip draws something honest rather than an error screen.
    """
    if raw is None:
        return None
    try:
        sequence = int(raw)
    except (TypeError, ValueError):
        return None
    return next((st for st in stop_times if st.sequence == sequence), None)


@api_view(['GET'])
@permission_classes([AllowAny])
def transit_journeys_view(request: Request) -> Response:
    """Direct rides AND one-transfer itineraries.

    Separate from `/search` on purpose: shipped builds have no leg concept and
    would render a two-bus journey as a single trip with the wrong route number
    and a stop list that walks through the interchange as if the rider never got
    off. Only clients that understand `legs` ask for this.
    """
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

    # `maxTransfers=0` asks for a single bus. Garbage is a client bug, not a
    # reason to 400 a search: fall back to the default rather than handing a
    # rider an error page because a query string was malformed.
    raw_max_transfers = request.GET.get('maxTransfers')
    max_transfers = None
    if raw_max_transfers is not None:
        try:
            max_transfers = int(raw_max_transfers)
        except (TypeError, ValueError):
            max_transfers = None

    with for_island(request.island):
        from transit.services.schedule_phase import resolve_dataset

        payload = search_journeys_v3(
            origin=origin,
            destination=destination,
            day=day,
            start_time=start,
            dataset=resolve_dataset(
                request.island, requested=request.GET.get('dataset'),
            ),
            max_transfers=max_transfers,
        )
        if payload is None:
            return Response(
                {'error': {'code': 'invalid_params', 'message': 'origin and destination are required'}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({'origin': origin, 'destination': destination, **payload})


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
        from transit.services.schedule_phase import resolve_dataset

        # Without this the dataset resolved from the server's own date, so every
        # AzoresBus trip 404'd while previewing pre-cutover -- the ids come from a
        # ?dataset=azoresbus search and could never be looked up again (03 §3).
        payload = get_trip_v3(
            trip_id,
            dataset=resolve_dataset(
                request.island, requested=request.GET.get('dataset'),
            ),
        )
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
        from transit.services.schedule_phase import resolve_dataset

        # Same gap as trip detail: line 101 exists in both networks, so a
        # previewed line has to be addressable too.
        payload = get_line_v3(
            line_code,
            dataset=resolve_dataset(
                request.island, requested=request.GET.get('dataset'),
            ),
        )
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
            # filter for defence (02 section 7.0). `dataset` is honoured so a
            # previewed trip can be voted on -- otherwise every vote on the
            # not-yet-active network 404s, exactly as trip detail did.
            trip = Trip.objects.filter(
                dataset=resolve_dataset(
                    request.island, requested=request.GET.get('dataset'),
                )
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
