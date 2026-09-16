from __future__ import annotations

from django.conf import settings
from mcp.types import ToolAnnotations

from mcp_server.bridge import run_in_island
from mcp_server.errors import error
from mcp_server.instance import mcp
from mcp_server.validation import parse_day, parse_start


def _dataset(island):
    from transit.services.schedule_phase import resolve_dataset
    return resolve_dataset(island)


def _stops_impl(island, query: str = '', limit: int = 20):
    dataset = _dataset(island)
    from assistant.services import clamp_limit, stop_finder
    from transit.models import Stop

    if query:
        return {'stops': stop_finder(dataset, query.strip(), limit=clamp_limit(limit, default=20, maximum=50))}
    from transit.services.v3 import serialize_stops_v3
    stops = Stop.objects.filter(dataset=dataset).order_by('name')[:clamp_limit(limit, default=20, maximum=50)]
    return {'stops': serialize_stops_v3(stops)}


def _stop_detail_impl(island, stop_id: int, day: str = 'weekday', start: str = '00:00'):
    dataset = _dataset(island)
    from transit.models import Stop
    from transit.services.stops import serialize_stop_detail
    stop = Stop.objects.filter(dataset=dataset).prefetch_related('external_stops').filter(id=stop_id).first()
    if stop is None:
        return error('not_found', 'Stop not found')
    return serialize_stop_detail(stop, day=parse_day(day), start_time=parse_start(start))


def _search_impl(island, origin: str, destination: str, day: str = 'weekday', start: str = '00:00'):
    dataset = _dataset(island)
    from transit.services.v3 import search_transit_v3
    result = search_transit_v3(origin=origin, destination=destination, day=parse_day(day), start_time=parse_start(start), dataset=dataset)
    return {'results': result or []}


def _journeys_impl(island, origin: str, destination: str, day: str = 'weekday', start: str = '00:00', max_transfers: int | None = None):
    dataset = _dataset(island)
    from transit.services.v3 import search_journeys_v3
    return search_journeys_v3(origin=origin, destination=destination, day=parse_day(day), start_time=parse_start(start), dataset=dataset, max_transfers=max_transfers)


def _trip_impl(island, trip_id: int):
    dataset = _dataset(island)
    from transit.services.v3 import get_trip_v3
    result = get_trip_v3(trip_id, dataset=dataset)
    return result or error('not_found', 'Trip not found')


def _line_impl(island, line_code: str):
    dataset = _dataset(island)
    from transit.services.v3 import get_line_v3
    result = get_line_v3(line_code, dataset=dataset)
    return result or error('not_found', 'Line not found')


def _tariffs_impl(island):
    from azoresbus.services_tariffs import current_snapshot, serialize_tariffs
    snapshot = current_snapshot(island)
    return serialize_tariffs(snapshot) if snapshot else error('not_found', 'No tariff snapshot has been synced yet')


@mcp.tool(name='transit_list_stops', annotations=ToolAnnotations(readOnlyHint=True))
async def transit_list_stops(query: str = '', limit: int = 20, island: str | None = None):
    return await run_in_island(_stops_impl, island, query, limit)


@mcp.tool(name='transit_find_stops', annotations=ToolAnnotations(readOnlyHint=True))
async def transit_find_stops(q: str, limit: int = 5, island: str | None = None):
    return await run_in_island(_stops_impl, island, q, limit)


@mcp.tool(name='transit_stop_detail', annotations=ToolAnnotations(readOnlyHint=True))
async def transit_stop_detail(stop_id: int, day: str = 'weekday', start: str = '00:00', island: str | None = None):
    return await run_in_island(_stop_detail_impl, island, stop_id, day, start)


@mcp.tool(name='transit_search', annotations=ToolAnnotations(readOnlyHint=True))
async def transit_search(origin: str, destination: str, day: str = 'weekday', start: str = '00:00', island: str | None = None):
    return await run_in_island(_search_impl, island, origin, destination, day, start)


@mcp.tool(name='transit_journeys', annotations=ToolAnnotations(readOnlyHint=True))
async def transit_journeys(origin: str, destination: str, day: str = 'weekday', start: str = '00:00', max_transfers: int | None = None, island: str | None = None):
    return await run_in_island(_journeys_impl, island, origin, destination, day, start, max_transfers)


@mcp.tool(name='transit_trip', annotations=ToolAnnotations(readOnlyHint=True))
async def transit_trip(trip_id: int, island: str | None = None):
    return await run_in_island(_trip_impl, island, trip_id)


@mcp.tool(name='transit_line', annotations=ToolAnnotations(readOnlyHint=True))
async def transit_line(line_code: str, island: str | None = None):
    return await run_in_island(_line_impl, island, line_code)


@mcp.tool(name='transit_tariffs', annotations=ToolAnnotations(readOnlyHint=True))
async def transit_tariffs(island: str | None = None):
    return await run_in_island(_tariffs_impl, island)