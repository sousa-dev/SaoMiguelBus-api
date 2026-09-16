from __future__ import annotations

from mcp.types import ToolAnnotations

from mcp_server.bridge import run_in_island
from mcp_server.errors import error
from mcp_server.instance import mcp


def _tracking_error(exc):
    from azoresbus.services_tracking import TrackingDisabled
    from azoresbus.tracking_client import AzoresbusTrackingError, AzoresbusVehicleNotFound
    if isinstance(exc, TrackingDisabled):
        return error('tracking_disabled', 'Live tracking is not enabled')
    if isinstance(exc, AzoresbusVehicleNotFound):
        return error('not_found', 'Vehicle not found')
    if isinstance(exc, AzoresbusTrackingError):
        return error('tracking_unavailable', 'Upstream AVL unavailable')
    return None


def _vehicles_impl(island):
    from azoresbus.services_tracking import get_fleet
    try:
        return {'vehicles': get_fleet(island)}
    except Exception as exc:  # mapped to stable public tool errors
        return _tracking_error(exc) or error('internal_error', 'The requested data could not be loaded')


def _vehicle_impl(island, vehicle_id: str):
    from azoresbus.services_tracking import get_vehicle
    try:
        return get_vehicle(island, vehicle_id)
    except Exception as exc:
        return _tracking_error(exc) or error('internal_error', 'The requested data could not be loaded')


def _arrivals_impl(island, stop_id: int):
    from azoresbus.services_arrivals import stop_arrivals
    try:
        return {'arrivals': stop_arrivals(island, stop_id)}
    except Exception as exc:
        return _tracking_error(exc) or error('internal_error', 'The requested data could not be loaded')


def _trips_impl(island, trip_ids: list[int]):
    from azoresbus.services_trip_live import live_for_trips
    try:
        return {'trips': live_for_trips(island, trip_ids[:5])}
    except Exception as exc:
        return _tracking_error(exc) or error('internal_error', 'The requested data could not be loaded')


@mcp.tool(name='azoresbus_vehicles', annotations=ToolAnnotations(readOnlyHint=True))
async def azoresbus_vehicles(island: str | None = None):
    return await run_in_island(_vehicles_impl, island)


@mcp.tool(name='azoresbus_vehicle', annotations=ToolAnnotations(readOnlyHint=True))
async def azoresbus_vehicle(vehicle_id: str, island: str | None = None):
    return await run_in_island(_vehicle_impl, island, vehicle_id)


@mcp.tool(name='azoresbus_stop_arrivals', annotations=ToolAnnotations(readOnlyHint=True))
async def azoresbus_stop_arrivals(stop_id: int, island: str | None = None):
    return await run_in_island(_arrivals_impl, island, stop_id)


@mcp.tool(name='azoresbus_trips_live', annotations=ToolAnnotations(readOnlyHint=True))
async def azoresbus_trips_live(trip_ids: list[int], island: str | None = None):
    return await run_in_island(_trips_impl, island, trip_ids)