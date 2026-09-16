from starlette.testclient import TestClient
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from mcp_server.asgi import build_application


class HTTPAppTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @override_settings(MCP_ALLOWED_HOSTS=['testserver'], MCP_ALLOWED_ORIGINS=[])
    def test_health_and_browser_landing(self):
        with TestClient(build_application()) as client:
            self.assertEqual(client.get('/mcp/health').json()['status'], 'ok')
            response = client.get('/mcp')
            self.assertEqual(response.status_code, 200)
            self.assertIn('São Miguel Bus MCP', response.text)

    @override_settings(
        MCP_ALLOWED_HOSTS=['testserver'],
        MCP_ALLOWED_ORIGINS=[],
        MCP_AUTH_TOKEN='secret',
    )
    def test_wrong_bearer_token_is_rejected(self):
        with TestClient(build_application()) as client:
            response = client.get('/mcp/health')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers['www-authenticate'], 'Bearer')

    @override_settings(MCP_ALLOWED_HOSTS=['testserver'], MCP_ALLOWED_ORIGINS=[])
    def test_initialize_returns_server_info(self):
        payload = {
            'jsonrpc': '2.0',
            'id': 1,
            'method': 'initialize',
            'params': {
                'protocolVersion': '2025-06-18',
                'capabilities': {},
                'clientInfo': {'name': 'test', 'version': '0'},
            },
        }
        with TestClient(build_application()) as client:
            response = client.post(
                '/mcp',
                headers={
                    'content-type': 'application/json',
                    'accept': 'application/json, text/event-stream',
                },
                json=payload,
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['result']['serverInfo']['name'], 'saomiguelbus')

    @override_settings(
        MCP_ALLOWED_HOSTS=['testserver'],
        MCP_ALLOWED_ORIGINS=[],
        MCP_RATE_LIMIT='2/min',
    )
    def test_rate_limit_returns_429(self):
        with TestClient(build_application()) as client:
            responses = [client.get('/mcp/health') for _ in range(3)]
        self.assertEqual([response.status_code for response in responses], [200, 200, 429])

    @override_settings(MCP_ALLOWED_HOSTS=['api.saomiguelhub.com'], MCP_ALLOWED_ORIGINS=[])
    def test_bad_host_is_rejected_by_sdk_security(self):
        with TestClient(build_application()) as client:
            response = client.get('/mcp/health', headers={'host': 'testserver'})
        self.assertEqual(response.status_code, 421)

    @override_settings(
        MCP_ALLOWED_HOSTS=['testserver'],
        MCP_ALLOWED_ORIGINS=[],
        MCP_AUTH_TOKEN='secret',
    )
    def test_browser_landing_page_is_visible_even_when_a_bearer_token_is_configured(self):
        # Regression: the landing page is the one place that explains how to use
        # MCP_AUTH_TOKEN -- it must never itself require that token to view.
        with TestClient(build_application()) as client:
            response = client.get('/mcp')
        self.assertEqual(response.status_code, 200)
        self.assertIn('São Miguel Bus MCP', response.text)

    @override_settings(
        MCP_ALLOWED_HOSTS=['testserver'],
        MCP_ALLOWED_ORIGINS=[],
        MCP_AUTH_TOKEN='secret',
    )
    def test_actual_protocol_call_still_requires_the_bearer_token(self):
        with TestClient(build_application()) as client:
            response = client.post(
                '/mcp',
                headers={
                    'content-type': 'application/json',
                    'accept': 'application/json, text/event-stream',
                },
                json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'},
            )
        self.assertEqual(response.status_code, 401)