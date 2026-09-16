from __future__ import annotations

from mcp.types import ToolAnnotations

from mcp_server.bridge import run_in_island
from mcp_server.errors import error
from mcp_server.instance import mcp


def _parishes_impl(island):
    from weather.services import ATTRIBUTION, list_parish_weather
    from weather.open_meteo_client import OpenMeteoError
    try:
        return {'parishes': list_parish_weather(island), 'attribution': ATTRIBUTION}
    except OpenMeteoError as exc:
        return error('weather_unavailable', str(exc))


def _parish_impl(island, slug: str):
    from weather.models import Parish
    from weather.services import get_parish_weather
    from weather.open_meteo_client import OpenMeteoError
    parish = Parish.objects.filter(island=island, slug=slug, is_active=True).first()
    if parish is None:
        return error('not_found', 'Parish not found')
    try:
        return get_parish_weather(parish)
    except OpenMeteoError as exc:
        return error('weather_unavailable', str(exc))


@mcp.tool(name='weather_parishes', annotations=ToolAnnotations(readOnlyHint=True))
async def weather_parishes(island: str | None = None):
    return await run_in_island(_parishes_impl, island)


@mcp.tool(name='weather_parish', annotations=ToolAnnotations(readOnlyHint=True))
async def weather_parish(slug: str, island: str | None = None):
    return await run_in_island(_parish_impl, island, slug)