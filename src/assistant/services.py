"""Business logic for AI-assistant-facing endpoints (`/api/v3/ai/*`).

Everything here is READ-ONLY and reuses the exact stop resolution and journey
search the rest of the API uses -- `search_journeys_v3` (`transit/services/v3.py`)
and `resolve_stop_ids` (`transit/services/search.py`) -- so an assistant is
never told about a bus `/api/v3/transit/journeys` would not also offer, and a
typo or an English tourist term never gets silently guessed into the wrong
stop. "A wrong line is worse than no line": a side that does not resolve comes
back as `resolved: {..: null}` plus `suggestions`, never a best-effort guess.
"""

from __future__ import annotations

import difflib
import re
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import quote, urlencode

from django.core.cache import cache
from django.utils import timezone

from assistant.aliases import STOP_ALIASES
from azoresbus.services_stops import build_azoresbus_area_index
from tenancy.models import Island
from tenancy.context import get_active_island
from transit.models import DATASET_AZORESBUS, Stop
from transit.services.journeys import resolve_service_day
from transit.services.schedule_phase import now_in_azores, resolve_dataset, today_in_azores
from transit.services.search import clean_string, resolve_stop_ids
from transit.services.v3 import search_journeys_v3

AI_LIMIT_DEFAULT = 5
AI_LIMIT_MAX = 10
STOP_LIMIT_DEFAULT = 5
STOP_LIMIT_MAX = 20

ATTRIBUTION = (
    'Data: São Miguel Bus (saomiguelbus.com), operator timetables. '
    'Please link to saomiguelbus.com when quoting.'
)
NOTES: list[str] = [
    'Times are local Azores time (Atlantic/Azores).',
    'Check the stop for last-minute changes.',
]

_WEEKDAY_NAMES = {
    'en': ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'),
    'pt': ('seg', 'ter', 'qua', 'qui', 'sex', 'sáb', 'dom'),
}
_MONTH_NAMES = {
    'en': ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'),
    'pt': ('jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'),
}


# ---------------------------------------------------------------------------
# Param parsing -- defensive on purpose. `transit/services/search.py`'s own
# `parse_time_parts` raises on anything that isn't a clean "H:MM"/"HhMM", and
# `clean_string('')` -> `''`, which `resolve_stop_ids`'s prefix fallback
# (`cleaned_name__startswith=''`) would match against EVERY stop in the
# dataset. Callers here guard both gaps before touching those helpers.
# ---------------------------------------------------------------------------


def clamp_limit(raw: str | None, *, default: int, maximum: int) -> int:
    if not raw:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(1, min(value, maximum))


def parse_date_param(raw: str | None) -> tuple[date, str]:
    """`date` query param -> (date, normalized `YYYY-MM-DD`). Default: today, Azores."""
    today = today_in_azores()
    if not raw or raw == 'today':
        return today, today.isoformat()
    if raw == 'tomorrow':
        tomorrow = today + timedelta(days=1)
        return tomorrow, tomorrow.isoformat()
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw):
        raise ValueError('date must be today, tomorrow, or YYYY-MM-DD')
    parsed = datetime.strptime(raw, '%Y-%m-%d').date()
    return parsed, parsed.isoformat()


def parse_time_param(raw: str | None) -> str:
    """`time` query param (`HH:MM`) -> normalized `HH:MM`. Default: now, Azores, rounded down."""
    if raw:
        if not re.fullmatch(r'\d{2}:\d{2}', raw):
            raise ValueError('time must be HH:MM')
        hour, minute = int(raw[:2]), int(raw[3:])
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError('time must be HH:MM')
        return raw
    now = now_in_azores()
    return f'{now.hour:02d}:{now.minute:02d}'


def normalize_lang(raw: str | None) -> str:
    return 'pt' if (raw or '').strip().lower().startswith('pt') else 'en'


# ---------------------------------------------------------------------------
# Stop resolution / fuzzy finder
# ---------------------------------------------------------------------------


def area_index_for(dataset: str) -> dict[str, set[int]] | None:
    return build_azoresbus_area_index(dataset) if dataset == DATASET_AZORESBUS else None


def stop_finder(
    dataset: str,
    query: str,
    *,
    limit: int = STOP_LIMIT_DEFAULT,
    area_index: dict[str, set[int]] | None = None,
) -> list[dict[str, Any]]:
    """Fuzzy stop finder over `Stop.cleaned_name`.

    Order: exact/alias/area/prefix (`resolve_stop_ids`, score 1.0) first, then
    the curated tourist-term alias table (`assistant.aliases`, score 0.95),
    then `difflib` fuzzy matches over every stop's cleaned name. A result here
    is ALWAYS offered as a suggestion the caller can retry with -- never used
    to silently resolve a journey search (see `resolve_stop_query`).
    """
    cleaned = clean_string(query)
    if not cleaned:
        return []
    if area_index is None:
        area_index = area_index_for(dataset)

    island = get_active_island()
    cache_key = f'assistant:stops:{island.pk}:{dataset}' if island else None
    stops = cache.get(cache_key) if cache_key else None
    if stops is None:
        stops = list(Stop.objects.filter(dataset=dataset).values(
            'id', 'name', 'cleaned_name', 'latitude', 'longitude',
        ))
        if cache_key:
            cache.set(cache_key, stops, 60)
    by_id = {stop['id']: stop for stop in stops}
    scored: dict[int, float] = {}

    for stop_id in resolve_stop_ids(dataset, cleaned, area_index):
        scored[stop_id] = 1.0

    alias_target = STOP_ALIASES.get(cleaned)
    if alias_target:
        alias_cleaned = clean_string(alias_target)
        for stop_id in resolve_stop_ids(dataset, alias_cleaned, area_index):
            scored.setdefault(stop_id, 0.95)

    cleaned_to_ids: dict[str, list[int]] = {}
    for stop in stops:
        cleaned_to_ids.setdefault(stop['cleaned_name'], []).append(stop['id'])

    fuzzy_targets = [cleaned]
    if alias_target:
        fuzzy_targets.append(clean_string(alias_target))

    for target in fuzzy_targets:
        for match in difflib.get_close_matches(
            target, cleaned_to_ids.keys(), n=limit, cutoff=0.6,
        ):
            ratio = difflib.SequenceMatcher(None, target, match).ratio()
            for stop_id in cleaned_to_ids[match]:
                scored[stop_id] = max(scored.get(stop_id, 0.0), round(ratio, 3))

    ranked = sorted(
        scored.items(), key=lambda pair: (-pair[1], by_id[pair[0]]['name']),
    )[:limit]

    return [
        {
            'id': stop_id,
            'name': by_id[stop_id]['name'],
            'latitude': by_id[stop_id]['latitude'],
            'longitude': by_id[stop_id]['longitude'],
            'score': score,
        }
        for stop_id, score in ranked
    ]


def resolve_stop_query(
    dataset: str, area_index: dict[str, set[int]] | None, raw: str,
) -> tuple[str | None, list[dict[str, Any]]]:
    """One side of a journey: (resolved canonical name, suggestions).

    Never guesses. A side that does not resolve gets `None` plus candidates
    from `stop_finder`, rather than the nearest prefix match standing in for
    what the caller actually asked for.
    """
    cleaned = clean_string(raw)
    if not cleaned:
        return None, []
    ids = resolve_stop_ids(dataset, cleaned, area_index)
    if ids:
        stop = Stop.objects.filter(id__in=ids).order_by('name').first()
        if stop is not None:
            if area_index and cleaned in area_index and len(ids) > 1:
                return stop.name.split(' (', 1)[0], []
            return stop.name, []
    return None, stop_finder(dataset, raw, limit=5, area_index=area_index)


# ---------------------------------------------------------------------------
# Journeys
# ---------------------------------------------------------------------------


def _format_date_human(day: date, lang: str) -> str:
    weekday = _WEEKDAY_NAMES[lang][day.weekday()]
    month = _MONTH_NAMES[lang][day.month - 1]
    return f'{weekday} {day.day} {month} {day.year}'


def _journey_ride_routes(journey: dict) -> list[str]:
    return [leg['route'] for leg in journey.get('legs', []) if leg.get('kind') == 'ride']


def _format_clock(hhmm: str) -> str:
    """`"08h30"` -> `"08:30"` for human-readable summaries/Markdown. The raw
    `journeys` list keeps `serialize_journeys`'s own `%Hh%M` format untouched --
    this is cosmetic only, for text an assistant reads aloud or quotes."""
    return hhmm.replace('h', ':') if isinstance(hhmm, str) and 'h' in hhmm else hhmm


def render_summary(
    *,
    lang: str,
    origin_label: str,
    destination_label: str,
    day_date: date,
    time_str: str,
    journeys: list[dict],
) -> str:
    date_human = _format_date_human(day_date, lang)

    if lang == 'pt':
        if not journeys:
            return (
                f'Não há autocarros de {origin_label} para {destination_label} '
                f'em {date_human} depois das {time_str}.'
            )
        head = (
            f'Próximos autocarros de {origin_label} para {destination_label} '
            f'em {date_human} depois das {time_str}: '
        )
        parts = []
        for journey in journeys:
            routes = ' + '.join(_journey_ride_routes(journey)) or '?'
            start, end = _format_clock(journey['start']), _format_clock(journey['end'])
            if journey.get('transfers', 0) == 0:
                parts.append(f'{start} linha {routes} (chegada {end}, direto)')
            else:
                parts.append(
                    f'{start} linha {routes} '
                    f'(chegada {end}, {journey["transfers"]} transbordo(s))'
                )
        return head + '; '.join(parts) + '.'

    if not journeys:
        return (
            f'No buses found from {origin_label} to {destination_label} '
            f'on {date_human} after {time_str}.'
        )
    head = (
        f'Next buses from {origin_label} to {destination_label} '
        f'on {date_human} after {time_str}: '
    )
    parts = []
    for journey in journeys:
        routes = ' + '.join(_journey_ride_routes(journey)) or '?'
        start, end = _format_clock(journey['start']), _format_clock(journey['end'])
        if journey.get('transfers', 0) == 0:
            parts.append(f'{start} line {routes} (arrives {end}, direct)')
        else:
            parts.append(
                f'{start} line {routes} (arrives {end}, {journey["transfers"]} change(s))'
            )
    return head + '; '.join(parts) + '.'


def build_ai_journeys(
    *,
    island: Island,
    origin_raw: str,
    destination_raw: str,
    date_raw: str | None,
    time_raw: str | None,
    lang_raw: str | None,
    limit_raw: str | None,
    transfers_raw: str | None,
    web_base_url: str,
    api_url: str,
) -> dict[str, Any]:
    """Full `/api/v3/ai/journeys` payload. Caller must already be inside
    `with for_island(island):` -- this function does no tenancy binding."""
    lang = normalize_lang(lang_raw)
    day_date, day_str = parse_date_param(date_raw)
    time_str = parse_time_param(time_raw)
    limit = clamp_limit(limit_raw, default=AI_LIMIT_DEFAULT, maximum=AI_LIMIT_MAX)
    max_transfers = 0 if transfers_raw == '0' else 1

    # `resolve_dataset(island)` -- NEVER pass `requested=` here. That kwarg is
    # the admin/preview toggle; populating it from a public query param would
    # let any caller force the legacy or preview network (schedule_phase.py
    # docstring, 98 §4).
    dataset = resolve_dataset(island)
    area_index = area_index_for(dataset)

    resolved_from, suggestions_from = resolve_stop_query(dataset, area_index, origin_raw)
    resolved_to, suggestions_to = resolve_stop_query(dataset, area_index, destination_raw)

    service_type, _ = resolve_service_day(day_str)
    day_type = service_type.lower()

    journeys: list[dict] = []
    if resolved_from and resolved_to:
        result = search_journeys_v3(
            # Keep the original terms: the journey engine resolves area keys
            # to a union of stops. A display label can only name one stop.
            origin=origin_raw,
            destination=destination_raw,
            day=day_str,
            start_time=time_str,
            dataset=dataset,
            max_transfers=max_transfers,
        ) or {}
        journeys = list(result.get('journeys') or [])[:limit]

    suggestions: dict[str, list[dict]] = {}
    if not resolved_from:
        suggestions['from'] = suggestions_from
    if not resolved_to:
        suggestions['to'] = suggestions_to

    if not resolved_from or not resolved_to:
        missing = ', '.join(
            label for label, resolved in (
                (origin_raw, resolved_from), (destination_raw, resolved_to),
            ) if not resolved
        )
        summary = (
            f'Não foi possível identificar a paragem: {missing}. Veja as sugestões e tente novamente.'
            if lang == 'pt' else
            f'Could not identify the stop: {missing}. Check the suggestions and retry.'
        )
    else:
        summary = render_summary(
            lang=lang,
            origin_label=resolved_from,
            destination_label=resolved_to,
            day_date=day_date,
            time_str=time_str,
            journeys=journeys,
        )

    web_query = urlencode(
        {
            'origin': resolved_from or origin_raw,
            'destination': resolved_to or destination_raw,
        },
        quote_via=quote,
    )
    web_link = f'{web_base_url.rstrip("/")}/transit?{web_query}'

    return {
        'query': {
            'from': origin_raw,
            'to': destination_raw,
            'date': day_str,
            'time': time_str,
            'dayType': day_type,
        },
        'resolved': {'from': resolved_from, 'to': resolved_to},
        'journeys': journeys,
        'summary': summary,
        'suggestions': suggestions,
        'links': {'web': web_link, 'api': api_url},
        'attribution': ATTRIBUTION,
        'notes': list(NOTES),
        'generatedAt': timezone.now().isoformat(),
    }


def render_markdown(payload: dict[str, Any]) -> str:
    """Same answer as the JSON payload, as a short Markdown block. Web-fetch
    tools digest Markdown more reliably than nested JSON."""
    query = payload['query']
    resolved = payload['resolved']
    from_label = resolved.get('from') or query['from']
    to_label = resolved.get('to') or query['to']

    lines = [
        f'# Buses: {from_label} → {to_label}',
        '',
        f'_{query["date"]} ({query["dayType"]}), from {query["time"]}, Atlantic/Azores time._',
        '',
    ]

    if payload['journeys']:
        lines.append('| Departs | Arrives | Route | Transfers |')
        lines.append('|---|---|---|---|')
        for journey in payload['journeys']:
            routes = ' + '.join(_journey_ride_routes(journey)) or '?'
            start, end = _format_clock(journey['start']), _format_clock(journey['end'])
            lines.append(f'| {start} | {end} | {routes} | {journey["transfers"]} |')
    else:
        lines.append(
            '_Could not identify a stop; retry with a suggested name._'
            if any(value is None for value in resolved.values()) else
            '_No journeys found for this search._'
        )
        for side, candidates in payload.get('suggestions', {}).items():
            if candidates:
                names = ', '.join(candidate['name'] for candidate in candidates)
                lines.append(f'- Did you mean ({side}): {names}?')

    lines += [
        '',
        payload['summary'],
        '',
        f'[View live schedule on saomiguelbus.com]({payload["links"]["web"]})',
        '',
        f'_{payload["attribution"]}_',
    ]
    return '\n'.join(lines) + '\n'
