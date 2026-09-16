from __future__ import annotations

from django.conf import settings
from django.http import JsonResponse

from mcp_server.tools import TOOL_NAMES


def discovery_view(request):
    token_option = ' --header "Authorization: Bearer …"' if settings.MCP_AUTH_TOKEN else ''
    url = settings.MCP_PUBLIC_URL
    return JsonResponse({
        'name': settings.MCP_SERVER_NAME,
        'endpoint': url,
        'transport': 'streamable-http',
        'auth': 'bearer' if settings.MCP_AUTH_TOKEN else 'none',
        'rateLimit': settings.MCP_RATE_LIMIT,
        'tools': TOOL_NAMES,
        'snippets': {
            'claudeCode': f'claude mcp add --transport http saomiguelbus {url}{token_option}',
            'cursor': '{"mcpServers":{"saomiguelbus":{"url":"' + url + '"}}}',
            'localStdio': 'python manage.py mcp_serve --stdio',
        },
    })