"""Self-description files served at the domain root: `/llms.txt`,
`/llms-full.txt`, `/robots.txt`, `/openapi.json`.

Plain Django views (not DRF) -- these are text a crawler requests directly and
digests as-is, with no JSON envelope. Registered in `src/src/urls.py` under
`if 'assistant' in settings.INSTALLED_APPS:`, same pattern as every other
conditional include there.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from drf_spectacular.renderers import OpenApiJsonRenderer, OpenApiJsonRenderer2
from drf_spectacular.views import SpectacularAPIView

from agent_docs.manifest import get_document
from assistant.bots import detect_bot
from tenancy.bootstrap import serialize_bootstrap
from tenancy.services import for_island

logger = logging.getLogger(__name__)

_FALLBACK_QUICKSTART = (
    '# São Miguel Bus\n\n'
    '> Machine-readable docs: /api/v3/agent-docs/ . '
    'Live journeys: /api/v3/ai/journeys?from=&to=\n'
)

_ENDPOINT_REFERENCE = '\n'.join(
    [
        '## Full endpoint reference',
        '',
        '- `GET /api/v3/ai/journeys?from=&to=&date=&time=&lang=&limit=&transfers=&format=` '
        '— real departures between two named stops, with a quotable `summary` '
        'and a deep link back to saomiguelbus.com',
        '- `GET /api/v3/ai/stops?q=&limit=` — fuzzy stop finder '
        '(exact, alias, area, prefix, then typo-tolerant fuzzy match)',
        '- `GET /api/v3/transit/search?origin=&destination=&day=&start=` '
        '— single-bus search',
        '- `GET /api/v3/transit/journeys?origin=&destination=&day=&start=` '
        '— direct rides and one-transfer itineraries',
        '- `GET /api/v3/agent-docs/` — catalog of machine-readable docs',
        '- `GET /api/v3/agent-docs/{slug}` — one doc (`?raw=1` for plain text)',
        '- `GET /api/schema/` — OpenAPI 3 schema '
        '(YAML by default; `Accept: application/vnd.oai.openapi+json`, or `/openapi.json`, for JSON)',
        '- `GET /api/docs/` — Swagger UI',
        '',
    ]
)


def _log_llms_hit(request: HttpRequest) -> None:
    user_agent = request.headers.get('User-Agent', '')
    logger.info(
        'assistant_hit',
        extra={'ua': user_agent, 'path': request.path, 'bot': detect_bot(user_agent)},
    )


def _quickstart_body() -> str:
    document = get_document('ai-quickstart')
    if document is None or not document.exists():
        return _FALLBACK_QUICKSTART
    return document.read_text()


def _rendered_quickstart(request: HttpRequest) -> str:
    body = _quickstart_body()
    island = getattr(request, 'island', None)
    if island is None:
        return body.replace('{{island_name}}', 'São Miguel').replace('{{modules}}', 'transit')
    with for_island(island):
        bootstrap = serialize_bootstrap(island)
    island_info = bootstrap['island']
    modules = ', '.join(island_info['enabledModules']) or 'transit'
    return body.replace('{{island_name}}', island_info['name']).replace('{{modules}}', modules)


def llms_txt_view(request: HttpRequest) -> HttpResponse:
    """llmstxt.org-shaped index: `## How to get bus times`, `## Other data`,
    `## Docs`. Single source of truth is `agent_docs/docs/ai-quickstart.md`."""
    _log_llms_hit(request)
    response = HttpResponse(_rendered_quickstart(request), content_type='text/plain; charset=utf-8')
    response['Cache-Control'] = 'public, max-age=3600'
    return response


def llms_full_txt_view(request: HttpRequest) -> HttpResponse:
    """`ai-quickstart.md` plus the full endpoint reference."""
    _log_llms_hit(request)
    body = _rendered_quickstart(request) + '\n\n' + _ENDPOINT_REFERENCE
    response = HttpResponse(body, content_type='text/plain; charset=utf-8')
    response['Cache-Control'] = 'public, max-age=3600'
    return response


def robots_txt_view(request: HttpRequest) -> HttpResponse:
    lines = [
        'User-agent: *',
        'Allow: /',
        'Allow: /llms.txt',
        'Allow: /llms-full.txt',
        'Allow: /api/schema/',
        'Allow: /api/v3/ai/',
        'Allow: /api/v3/agent-docs/',
        'Disallow: /dashboard/',
        'Disallow: /accounts/',
        '',
        '# AI assistants: start at /llms.txt',
    ]
    return HttpResponse('\n'.join(lines) + '\n', content_type='text/plain; charset=utf-8')


class OpenAPIJSONView(SpectacularAPIView):
    """`/openapi.json` -- exactly `/api/schema/`, but always JSON.

    Some agentic fetchers request `/openapi.json` by filename convention and
    never send `Accept: application/vnd.oai.openapi+json`, so this forces the
    JSON renderer instead of relying on content negotiation picking YAML.
    """

    renderer_classes = [OpenApiJsonRenderer, OpenApiJsonRenderer2]
