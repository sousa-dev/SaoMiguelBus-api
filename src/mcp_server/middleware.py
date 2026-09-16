from __future__ import annotations

import hmac
import re

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse


def _response(start, body: bytes, status: int, headers: list[tuple[bytes, bytes]] | None = None):
    base = [(b'content-type', b'text/plain; charset=utf-8'), (b'content-length', str(len(body)).encode())]
    return start({'type': 'http.response.start', 'status': status, 'headers': base + (headers or [])}), body


class BearerTokenMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        token = getattr(settings, 'MCP_AUTH_TOKEN', '')
        if scope['type'] != 'http' or not token:
            return await self.app(scope, receive, send)
        authorization = dict(scope.get('headers', [])).get(b'authorization', b'').decode()
        provided = authorization[7:] if authorization.lower().startswith('bearer ') else ''
        if not hmac.compare_digest(provided, token):
            body = b'Unauthorized'
            await send({'type': 'http.response.start', 'status': 401, 'headers': [(b'www-authenticate', b'Bearer'), (b'content-type', b'text/plain'), (b'content-length', str(len(body)).encode())]})
            await send({'type': 'http.response.body', 'body': body})
            return
        await self.app(scope, receive, send)


class HostValidationMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        allowed_hosts = getattr(settings, 'MCP_ALLOWED_HOSTS', [])
        host = dict(scope.get('headers', [])).get(b'host', b'').decode().lower()
        hostname = host.split(':', 1)[0]
        allowed = {configured.strip().lower() for configured in allowed_hosts if configured.strip()}
        host_allowed = any(
            (rule.endswith(':*') and host.startswith(rule[:-1]))
            or rule == host
            or (':' not in rule and rule == hostname)
            for rule in allowed
        )
        if allowed and not host_allowed:
            body = b'Misdirected Request'
            await send({
                'type': 'http.response.start',
                'status': 421,
                'headers': [
                    (b'content-type', b'text/plain; charset=utf-8'),
                    (b'content-length', str(len(body)).encode()),
                ],
            })
            await send({'type': 'http.response.body', 'body': body})
            return
        await self.app(scope, receive, send)


class RateLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        match = re.fullmatch(
            r'\s*(\d+)\s*/\s*(s|second|m|min|minute|h|hour)\s*',
            getattr(settings, 'MCP_RATE_LIMIT', '120/min'),
        )
        if not match:
            return await self.app(scope, receive, send)
        limit, unit = int(match.group(1)), match.group(2)
        duration = {
            's': 1,
            'second': 1,
            'm': 60,
            'min': 60,
            'minute': 60,
            'h': 3600,
            'hour': 3600,
        }[unit]
        client = (scope.get('client') or ('unknown', 0))[0]
        key = f'mcp:rate:{client}:{duration}'
        try:
            added = cache.add(key, 1, duration)
            current = 1 if added else cache.incr(key)
            if current > limit:
                body = b'Too Many Requests'
                await send({'type': 'http.response.start', 'status': 429, 'headers': [(b'retry-after', str(duration).encode()), (b'content-type', b'text/plain'), (b'content-length', str(len(body)).encode())]})
                await send({'type': 'http.response.body', 'body': body})
                return
        except Exception:  # noqa: BLE001 - availability beats throttling
            pass
        await self.app(scope, receive, send)


class HumanLandingMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        accept = dict(scope.get('headers', [])).get(b'accept', b'').decode().lower()
        path = scope.get('path', '')
        if scope['type'] == 'http' and scope['method'] == 'GET' and path.rstrip('/') == '/mcp' and 'text/event-stream' not in accept:
            from django.template.loader import render_to_string
            body = render_to_string(
                'mcp_server/landing.html',
                {'tools': await _tool_names()},
            ).encode()
            await send({'type': 'http.response.start', 'status': 200, 'headers': [(b'content-type', b'text/html; charset=utf-8'), (b'content-length', str(len(body)).encode())]})
            await send({'type': 'http.response.body', 'body': body})
            return
        await self.app(scope, receive, send)


async def _tool_names():
    from mcp_server.instance import mcp
    return [tool.name for tool in await mcp.list_tools()]