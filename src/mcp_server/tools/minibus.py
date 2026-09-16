from __future__ import annotations

from django.apps import apps
from django.conf import settings
from mcp.types import ToolAnnotations

from mcp_server.bridge import run_in_island
from mcp_server.errors import error
from mcp_server.instance import mcp


class _UrlBuilder:
    def build_absolute_uri(self, path: str) -> str:
        return f'{settings.MCP_PUBLIC_API_URL.rstrip("/")}{path}'


def _guard():
    if not apps.is_installed('minibus'):
        return error('module_unavailable', 'Mini Bus is not enabled')
    return None


def _lines_impl(island, locale: str = 'pt'):
    if (problem := _guard()):
        return problem
    from minibus.models import MinibusLine
    from minibus.services import serialize_line
    request = _UrlBuilder()
    lines = MinibusLine.objects.filter(island=island, is_active=True).order_by('sort_order', 'code')
    return {'lines': [serialize_line(line, locale=locale, request=request) for line in lines]}


def _line_impl(island, slug: str, locale: str = 'pt'):
    if (problem := _guard()):
        return problem
    from minibus.models import MinibusLine
    from minibus.services import serialize_line
    line = MinibusLine.objects.filter(island=island, slug=slug, is_active=True).first()
    return serialize_line(line, locale=locale, request=_UrlBuilder()) if line else error('not_found', 'Mini Bus line not found')


def _route_impl(island, origin: str, destination: str, locale: str = 'pt'):
    if (problem := _guard()):
        return problem
    from minibus.services import search_minibus_routes
    return search_minibus_routes(island=island, origin=origin, destination=destination, locale=locale)


@mcp.tool(name='minibus_lines', annotations=ToolAnnotations(readOnlyHint=True))
async def minibus_lines(locale: str = 'pt', island: str | None = None):
    return await run_in_island(_lines_impl, island, locale)


@mcp.tool(name='minibus_line', annotations=ToolAnnotations(readOnlyHint=True))
async def minibus_line(slug: str, locale: str = 'pt', island: str | None = None):
    return await run_in_island(_line_impl, island, slug, locale)


@mcp.tool(name='minibus_route', annotations=ToolAnnotations(readOnlyHint=True))
async def minibus_route(origin: str, destination: str, locale: str = 'pt', island: str | None = None):
    return await run_in_island(_route_impl, island, origin, destination, locale)