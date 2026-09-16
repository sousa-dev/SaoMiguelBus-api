from __future__ import annotations

from contextlib import asynccontextmanager

from django.conf import settings
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from mcp.server.transport_security import TransportSecuritySettings

from mcp_server.middleware import (
    BearerTokenMiddleware,
    HostValidationMiddleware,
    HumanLandingMiddleware,
    RateLimitMiddleware,
)
from mcp_server.server import mcp


async def health(request):
    return JSONResponse({'status': 'ok', 'name': settings.MCP_SERVER_NAME})


def build_application():
    @asynccontextmanager
    async def lifespan(app):
        async with mcp.session_manager.run():
            yield

    security = TransportSecuritySettings(
        allowed_hosts=settings.MCP_ALLOWED_HOSTS,
        allowed_origins=settings.MCP_ALLOWED_ORIGINS,
    )
    mcp_app = mcp.streamable_http_app(
        streamable_http_path='/mcp',
        stateless_http=True,
        json_response=True,
        transport_security=security,
        host=settings.MCP_HOST,
    )
    app = Starlette(
        routes=[Route('/mcp/health', health), Mount('/', app=mcp_app)],
        lifespan=lifespan,
    )
    # HumanLandingMiddleware sits OUTERMOST: a browser hitting GET /mcp for
    # the instructions page must see it regardless of MCP_AUTH_TOKEN/allowed-host
    # config -- otherwise setting a token (the brief's own auth option) makes the
    # one page that explains how to use that token invisible behind a bare 401.
    # Everything else (the real MCP protocol traffic, /mcp/health) still goes
    # through Bearer auth, host validation, and rate limiting unchanged.
    return HumanLandingMiddleware(
        BearerTokenMiddleware(HostValidationMiddleware(RateLimitMiddleware(app)))
    )


application = build_application()