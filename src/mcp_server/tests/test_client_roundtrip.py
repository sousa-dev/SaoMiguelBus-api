"""End-to-end round trip through the real MCP protocol layer (in-memory
transport, no HTTP) -- confirms tool registration, argument parsing, and the
`dict` return shape actually reach a real MCP client, not just the sync impl.

Uses `TransactionTestCase` because the tool call runs inside `sync_to_async`
on a worker thread; a plain `TestCase`'s wrapping transaction is not visible
to a different DB connection, so fixtures must be genuinely committed.

The tool functions are annotated `-> dict[str, Any]`-free (plain `dict`
returns with no declared return type), so the SDK does not populate
`CallToolResult.structured_content` for them -- it serializes the dict to a
single JSON `TextContent` block instead. Confirmed by direct inspection
against a running server (see the plan's own caveat: verify this rather than
assume `structured_content`, and adjust the assertion, not the tools). Parse
`result.content[0].text` as JSON here rather than changing the tools' return
type just to satisfy a test.
"""

from __future__ import annotations

import asyncio
import json

from django.test import TransactionTestCase
from mcp import Client

from transit.models import ServicePattern
from transit.tests.fixtures import ensure_transit_fixtures
from tenancy.services import for_island
from mcp_server.server import mcp


class ClientRoundtripTestCase(TransactionTestCase):
    def test_tool_list_and_known_trip_lookup(self):
        island, trip, line = ensure_transit_fixtures()
        with for_island(island):
            service, _ = ServicePattern.objects.get_or_create(
                island=island, key='mcp-roundtrip-weekdays',
                defaults={day: True for day in ServicePattern.WEEKDAY_FIELDS[:5]},
            )
            trip.service = service
            trip.save(update_fields=['service'])

        async def run():
            async with Client(mcp) as client:
                tools = await client.list_tools()
                result = await client.call_tool('transit_trip', {'trip_id': trip.id})
                return tools, result

        tools, result = asyncio.run(run())

        tool_names = {tool.name for tool in tools.tools}
        self.assertIn('transit_journeys', tool_names)
        self.assertIn('transit_trip', tool_names)
        self.assertFalse(result.is_error)

    def test_unknown_trip_returns_structured_error_not_a_protocol_error(self):
        island, _trip, _line = ensure_transit_fixtures()

        async def run():
            async with Client(mcp) as client:
                return await client.call_tool('transit_trip', {'trip_id': 999999})

        result = asyncio.run(run())
        self.assertFalse(result.is_error)
        payload = json.loads(result.content[0].text)
        self.assertEqual(payload['error']['code'], 'not_found')
