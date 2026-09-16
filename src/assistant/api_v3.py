"""AI-assistant-facing v3 API -- GET-only, unauthenticated, real bus data.

`/api/v3/ai/journeys` and `/api/v3/ai/stops` exist so a browsing-enabled AI
assistant (ChatGPT search, Claude web search, Perplexity, ...) that has
already found saomiguelbus.com can call one plain GET URL and answer with a
real departure instead of "no buses" or a hallucinated one. Nothing here
touches `transit/api_v3.py` or its response shapes -- both views are thin
wrappers around `assistant/services.py`, which itself only calls the existing
`transit.services.v3` / `transit.services.search` functions the rest of the
API already relies on.
"""

from __future__ import annotations

import hashlib
import logging

from django.conf import settings
from django.core.cache import cache
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, renderer_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response

from assistant.bots import detect_bot
from assistant.negotiation import AssistantContentNegotiation
from assistant.renderers import MarkdownRenderer
from assistant.services import (
    STOP_LIMIT_DEFAULT,
    STOP_LIMIT_MAX,
    build_ai_journeys,
    clamp_limit,
    parse_date_param,
    parse_time_param,
    render_markdown,
    stop_finder,
)
from assistant.throttling import AIThrottle
from tenancy.services import for_island
from transit.services.schedule_phase import resolve_dataset

logger = logging.getLogger(__name__)


def _require_island(request: Request) -> Response | None:
    if request.island is None:
        return Response(
            {'error': {'code': 'island_required', 'message': 'Island context required'}},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return None


def _log_assistant_hit(request: Request, **extra) -> None:
    """One structured line per `/api/v3/ai/*` hit -- the only way to know
    whether an assistant actually found and called this (98 §1.4)."""
    user_agent = request.headers.get('User-Agent', '')
    logger.info(
        'assistant_hit',
        extra={
            'ua': user_agent,
            'path': request.path,
            'bot': detect_bot(user_agent),
            **extra,
        },
    )


@extend_schema(
    summary='Find real bus journeys by stop name',
    description=(
        'Use named stops and an Azores-local date. Unknown names return no journeys '
        'and suggestions rather than a guessed stop. Examples are illustrative, '
        'not live timetables. `format=md` or '
        '`Accept: text/markdown` returns a compact Markdown answer.'
    ),
    parameters=[
        OpenApiParameter('from', str, required=True, description='Origin stop or area name'),
        OpenApiParameter('to', str, required=True, description='Destination stop or area name'),
        OpenApiParameter('date', str, description='YYYY-MM-DD, today, or tomorrow; default today in Atlantic/Azores'),
        OpenApiParameter('time', str, description='HH:MM; default current Azores time'),
        OpenApiParameter('lang', str, enum=['en', 'pt']),
        OpenApiParameter('limit', int, description='Default 5, maximum 10'),
        OpenApiParameter('transfers', int, enum=[0, 1]),
        OpenApiParameter('format', str, enum=['json', 'md']),
    ],
    examples=[OpenApiExample(
        'Illustrative journey response (not live timetable)',
        value={'query': {'from': 'Ponta Delgada', 'to': 'Ribeira Grande', 'date': '2026-09-15', 'time': '08:00', 'dayType': 'weekday'},
               'resolved': {'from': 'Ponta Delgada', 'to': 'Ribeira Grande'},
               'journeys': [{'id': '42-1', 'transfers': 0, 'start': '08h30', 'end': '09h15',
                             'durationMinutes': 45, 'waitMinutes': 0, 'dayOffset': 0,
                             'typeOfDay': 'WEEKDAY',
                             'legs': [{'kind': 'ride', 'tripId': 42, 'route': '208',
                                       'likesPercent': 100, 'dislikesPercent': 0,
                                       'information': {},
                                       'board': {'name': 'Ponta Delgada', 'time': '08h30', 'sequence': 1, 'dayOffset': 0},
                                       'alight': {'name': 'Ribeira Grande', 'time': '09h15', 'sequence': 2, 'dayOffset': 0},
                                       'stops': []}]}],
               'summary': 'Next buses from Ponta Delgada to Ribeira Grande on Tue 15 Sep 2026 after 08:00: 08:30 line 208 (arrives 09:15, direct).',
               'suggestions': {}, 'links': {'web': 'https://saomiguelbus.com/transit?origin=Ponta%20Delgada&destination=Ribeira%20Grande',
                                            'api': 'https://api.saomiguelhub.com/api/v3/ai/journeys?from=Ponta%20Delgada&to=Ribeira%20Grande'},
               'attribution': 'Data: São Miguel Bus (saomiguelbus.com), operator timetables.',
               'notes': ['Times are local Azores time (Atlantic/Azores).'],
               'generatedAt': '2026-09-15T08:12:00+00:00'}, response_only=True,
    )],
)

def _public_absolute_uri(request: Request) -> str:
    """`build_absolute_uri()` that survives a proxy when Django is not told to
    trust `X-Forwarded-Proto` (SECURE_PROXY_SSL_HEADER is only configured when
    DEBUG is off, and production has run with DEBUG on). Assistants copy this
    self-link verbatim, so it must never advertise plain http for an https
    deployment."""
    url = request.build_absolute_uri()
    forwarded_proto = request.META.get('HTTP_X_FORWARDED_PROTO', '').split(',')[0].strip()
    if url.startswith('http://') and (forwarded_proto == 'https' or request.is_secure()):
        return 'https://' + url[len('http://'):]
    return url

@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([AIThrottle])
@renderer_classes([JSONRenderer, MarkdownRenderer])
def ai_journeys_view(request: Request) -> Response:
    """Real journeys between two named stops, for an AI assistant to quote.

    Params: `from`* `to`* `date` (`YYYY-MM-DD`|`today`|`tomorrow`, default
    today, Atlantic/Azores) `time` (`HH:MM`, default now) `lang` (`en`|`pt`)
    `limit` (default 5, max 10) `transfers` (`0`|`1`, default 1)
    `format` (`json`|`md`; `Accept: text/markdown` also selects `md`).

    A side that does not resolve to a known stop never gets guessed -- the
    response comes back `200` with `journeys: []`, `resolved.<side>: null`
    and `suggestions.<side>` from the fuzzy stop finder instead.
    """
    err = _require_island(request)
    if err:
        _log_assistant_hit(request, resolved=None)
        return err

    origin = request.GET.get('from', '').strip()
    destination = request.GET.get('to', '').strip()
    if not origin or not destination:
        _log_assistant_hit(request, origin=origin, destination=destination, resolved=None)
        return Response(
            {'error': {'code': 'invalid_params', 'message': '"from" and "to" are required'}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        parse_date_param(request.GET.get('date'))
        parse_time_param(request.GET.get('time'))
    except ValueError as exc:
        _log_assistant_hit(request, origin=origin, destination=destination, resolved=None)
        return Response(
            {'error': {'code': 'invalid_params', 'message': str(exc)}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Cache the format-neutral answer for 60 seconds. The island and complete
    # URL are both part of the key so tenant data and self-links cannot leak.
    cache_key = 'assistant:journeys:' + hashlib.sha256(
        f'{request.island.pk}:{request.build_absolute_uri()}'.encode('utf-8')
    ).hexdigest()
    payload = cache.get(cache_key)
    if payload is None:
        with for_island(request.island):
            payload = build_ai_journeys(
                island=request.island,
                origin_raw=origin,
                destination_raw=destination,
                date_raw=request.GET.get('date'),
                time_raw=request.GET.get('time'),
                lang_raw=request.GET.get('lang'),
                limit_raw=request.GET.get('limit'),
                transfers_raw=request.GET.get('transfers'),
                web_base_url=settings.PROJECT_URL,
                api_url=_public_absolute_uri(request),
            )
        cache.set(cache_key, payload, 60)

    _log_assistant_hit(
        request,
        origin=origin,
        destination=destination,
        resolved=payload['resolved'],
    )

    wants_markdown = (
        request.GET.get('format') == 'md'
        or 'text/markdown' in request.headers.get('Accept', '')
    )
    if wants_markdown:
        return Response(render_markdown(payload), content_type='text/markdown; charset=utf-8')
    return Response(payload)


# Function-based DRF views expose their generated APIView class on `.cls`.
# DRF has no function decorator for `content_negotiation_class`.
ai_journeys_view.cls.content_negotiation_class = AssistantContentNegotiation


@extend_schema(
    summary='Find stops by name, typo, or tourist term',
    description='Returns suggestions only; use the returned name in a journey search.',
    parameters=[OpenApiParameter('q', str, required=True), OpenApiParameter('limit', int, description='Default 5, maximum 20')],
    examples=[OpenApiExample('Airport suggestion', value={'query': 'airport', 'stops': [{'id': 123, 'name': 'Aeroporto', 'latitude': 37.74, 'longitude': -25.69, 'score': 0.95}]}, response_only=True)],
)
@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([AIThrottle])
def ai_stops_view(request: Request) -> Response:
    """Fuzzy stop finder: exact/alias/area/prefix first, then a typo-tolerant
    fuzzy match plus a small curated English/tourist-term alias table."""
    err = _require_island(request)
    if err:
        _log_assistant_hit(request, q=request.GET.get('q', ''))
        return err

    query = request.GET.get('q', '').strip()
    limit = clamp_limit(
        request.GET.get('limit'), default=STOP_LIMIT_DEFAULT, maximum=STOP_LIMIT_MAX,
    )

    with for_island(request.island):
        dataset = resolve_dataset(request.island)
        stops = stop_finder(dataset, query, limit=limit) if query else []

    _log_assistant_hit(request, q=query)

    return Response({'query': query, 'stops': stops})
