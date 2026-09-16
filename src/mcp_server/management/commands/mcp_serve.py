from __future__ import annotations

import asyncio

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Run the São Miguel Bus MCP server.'

    def add_arguments(self, parser):
        parser.add_argument('--host', default=settings.MCP_HOST)
        parser.add_argument('--port', default=settings.MCP_PORT, type=int)
        parser.add_argument('--reload', action='store_true')
        parser.add_argument('--stdio', action='store_true')

    def handle(self, *args, **options):
        if options['stdio']:
            from mcp_server.server import mcp
            asyncio.run(mcp.run_stdio_async())
            return
        import uvicorn
        uvicorn.run(
            'mcp_server.asgi:application',
            host=options['host'],
            port=options['port'],
            reload=options['reload'],
            proxy_headers=True,
            forwarded_allow_ips='*',
        )