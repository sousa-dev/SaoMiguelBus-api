"""Read-side analytics API (AUTH_KEY protected) for the stats dashboard."""

from __future__ import annotations

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from analytics import services_reporting as reporting


def _auth_key_from_request(request: Request) -> str:
    return (
        request.query_params.get('key')
        or request.headers.get('X-Auth-Key')
        or request.headers.get('X-Api-Key')
        or ''
    )


def _denied(request: Request) -> Response | None:
    if _auth_key_from_request(request) != settings.AUTH_KEY:
        return Response(
            {'error': {'code': 'unauthorized', 'message': 'Valid AUTH_KEY required'}},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    return None


def _require_island(request: Request) -> Response | None:
    if request.island is None:
        return Response(
            {'error': {'code': 'island_required', 'message': 'Island context required'}},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return None


def _q(request: Request, name: str) -> str | None:
    value = request.query_params.get(name)
    return value.strip() if value and value.strip() else None


def _flag(request: Request, name: str) -> bool:
    return (_q(request, name) or '').lower() in ('1', 'true', 'yes')


MAX_PROPERTY_FILTERS = 8


def _prop_filters(request: Request) -> dict[str, str]:
    """Collect ``prop.<key>=<value>`` params for JSON property filtering."""
    filters: dict[str, str] = {}
    for name, value in request.query_params.items():
        if not name.startswith('prop.') or not value.strip():
            continue
        key = name[len('prop.'):].strip()
        if key:
            filters[key] = value.strip()
        if len(filters) >= MAX_PROPERTY_FILTERS:
            break
    return filters


def _int_or_none(raw: str | None) -> int | None:
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


@api_view(['GET'])
@permission_classes([AllowAny])
def v3_overview_view(request: Request) -> Response:
    denied = _denied(request) or _require_island(request)
    if denied:
        return denied

    start, end = reporting.parse_range(_q(request, 'start'), _q(request, 'end'))
    interval = reporting.resolve_interval(start, end, _q(request, 'interval'))
    payload = reporting.v3_overview(
        island=request.island,
        start=start,
        end=end,
        interval=interval,
        module=_q(request, 'module'),
        event_type=_q(request, 'event_type'),
        platform=_q(request, 'platform'),
        locale=_q(request, 'locale'),
        properties=_prop_filters(request),
        compare=_flag(request, 'compare'),
    )
    return Response(payload)


@api_view(['GET'])
@permission_classes([AllowAny])
def v3_events_view(request: Request) -> Response:
    denied = _denied(request) or _require_island(request)
    if denied:
        return denied

    start, end = reporting.parse_range(_q(request, 'start'), _q(request, 'end'))
    page, page_size = reporting.paginate_params(_q(request, 'page'), _q(request, 'page_size'))
    payload = reporting.v3_events(
        island=request.island,
        start=start,
        end=end,
        page=page,
        page_size=page_size,
        module=_q(request, 'module'),
        event_type=_q(request, 'event_type'),
        platform=_q(request, 'platform'),
        locale=_q(request, 'locale'),
        properties=_prop_filters(request),
    )
    return Response(payload)


@api_view(['GET'])
@permission_classes([AllowAny])
def v3_properties_view(request: Request) -> Response:
    denied = _denied(request) or _require_island(request)
    if denied:
        return denied

    start, end = reporting.parse_range(_q(request, 'start'), _q(request, 'end'))
    payload = reporting.v3_properties(
        island=request.island,
        start=start,
        end=end,
        module=_q(request, 'module'),
        event_type=_q(request, 'event_type'),
        platform=_q(request, 'platform'),
        locale=_q(request, 'locale'),
        properties=_prop_filters(request),
        key=_q(request, 'prop'),
    )
    return Response(payload)


@api_view(['GET'])
@permission_classes([AllowAny])
def v3_meta_view(request: Request) -> Response:
    denied = _denied(request) or _require_island(request)
    if denied:
        return denied
    return Response(reporting.v3_meta(request.island))


@api_view(['GET'])
@permission_classes([AllowAny])
def legacy_overview_view(request: Request) -> Response:
    denied = _denied(request)
    if denied:
        return denied

    start, end = reporting.parse_range(_q(request, 'start'), _q(request, 'end'))
    interval = reporting.resolve_interval(start, end, _q(request, 'interval'))
    payload = reporting.legacy_overview(
        start=start,
        end=end,
        interval=interval,
        request_type=_q(request, 'request'),
        platform=_q(request, 'platform'),
        language=_q(request, 'language'),
        origin=_q(request, 'origin'),
        destination=_q(request, 'destination'),
        compare=_flag(request, 'compare'),
    )
    return Response(payload)


@api_view(['GET'])
@permission_classes([AllowAny])
def legacy_events_view(request: Request) -> Response:
    denied = _denied(request)
    if denied:
        return denied

    start, end = reporting.parse_range(_q(request, 'start'), _q(request, 'end'))
    page, page_size = reporting.paginate_params(_q(request, 'page'), _q(request, 'page_size'))
    payload = reporting.legacy_events(
        start=start,
        end=end,
        page=page,
        page_size=page_size,
        request_type=_q(request, 'request'),
        platform=_q(request, 'platform'),
        language=_q(request, 'language'),
        origin=_q(request, 'origin'),
        destination=_q(request, 'destination'),
    )
    return Response(payload)


@api_view(['GET'])
@permission_classes([AllowAny])
def legacy_meta_view(request: Request) -> Response:
    denied = _denied(request)
    if denied:
        return denied
    return Response(reporting.legacy_meta())


@api_view(['GET'])
@permission_classes([AllowAny])
def transit_overview_view(request: Request) -> Response:
    denied = _denied(request) or _require_island(request)
    if denied:
        return denied

    start, end = reporting.parse_range(_q(request, 'start'), _q(request, 'end'))
    interval = reporting.resolve_interval(start, end, _q(request, 'interval'))
    payload = reporting.unified_transit_overview(
        island=request.island,
        start=start,
        end=end,
        interval=interval,
        platform=_q(request, 'platform'),
        origin=_q(request, 'origin'),
        destination=_q(request, 'destination'),
        compare=_flag(request, 'compare'),
    )
    return Response(payload)


@api_view(['GET'])
@permission_classes([AllowAny])
def ads_overview_view(request: Request) -> Response:
    denied = _denied(request) or _require_island(request)
    if denied:
        return denied

    start, end = reporting.parse_range(_q(request, 'start'), _q(request, 'end'))
    interval = reporting.resolve_interval(start, end, _q(request, 'interval'))
    payload = reporting.ads_overview(
        island=request.island,
        start=start,
        end=end,
        interval=interval,
        ad_id=_int_or_none(_q(request, 'ad_id')),
        platform=_q(request, 'platform'),
        compare=_flag(request, 'compare'),
    )
    return Response(payload)
