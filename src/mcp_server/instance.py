from __future__ import annotations

from mcp.server import MCPServer


GUIDE = (
    'São Miguel Bus public MCP server. Use the transit tools for real Azores-local '
    'schedules, and the live, weather, and PDL Mini Bus tools for current data.'
)

mcp = MCPServer(name='saomiguelbus', instructions=GUIDE, version='3.0.0')