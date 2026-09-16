from __future__ import annotations

TOOL_NAMES = [
	'transit_list_stops', 'transit_find_stops', 'transit_stop_detail',
	'transit_search', 'transit_journeys', 'transit_trip', 'transit_line',
	'transit_tariffs', 'minibus_lines', 'minibus_line', 'minibus_route',
	'azoresbus_vehicles', 'azoresbus_vehicle', 'azoresbus_stop_arrivals',
	'azoresbus_trips_live', 'weather_parishes', 'weather_parish',
]

from mcp_server.tools import azoresbus, minibus, transit, weather  # noqa: F401,E402
