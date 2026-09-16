from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase, override_settings

from mcp_server.bridge import resolve_island_sync, run_in_island


class BridgeTests(SimpleTestCase):
    @override_settings(DEFAULT_ISLAND_KEY='missing')
    @patch('mcp_server.bridge.Island')
    def test_unknown_default_island_is_structured_error(self, Island):
        Island.objects.filter.return_value.first.return_value = None
        self.assertEqual(resolve_island_sync(None), {
            'error': {
                'code': 'unknown_island',
                'message': 'Unknown island: missing',
            },
        })

    def test_worker_maps_unexpected_exceptions_without_raising(self):
        def explode(_island):
            raise RuntimeError('upstream broke')

        with patch('mcp_server.bridge.resolve_island_sync') as resolve:
            resolve.return_value = object()
            result = async_to_sync(run_in_island)(explode, 'sao-miguel')

        self.assertEqual(result, {
            'error': {
                'code': 'internal_error',
                'message': 'The requested data could not be loaded',
            },
        })