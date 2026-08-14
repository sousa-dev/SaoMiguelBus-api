"""Tests for Eleven Systems AVL HTTP client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
import requests

from minibus.tracking_client import (
    MinibusTrackingError,
    MinibusTrackingNotFoundError,
    fetch_fleet_locations,
    fetch_vehicle_location,
)


class TrackingClientTestCase(SimpleTestCase):
    @patch('minibus.tracking_client.requests.get')
    @patch('minibus.tracking_client.MINIBUS_TRACKING_BASE_URL', 'https://example.test/publicapi')
    def test_fetch_fleet_locations_success(self, mock_get):
        mock_get.return_value = MagicMock(
            ok=True,
            status_code=200,
            json=lambda: [{'id': '11010939', 'status': 'ontime'}],
        )

        result = fetch_fleet_locations()

        self.assertEqual(result, [{'id': '11010939', 'status': 'ontime'}])
        mock_get.assert_called_once_with(
            'https://example.test/publicapi/locations',
            timeout=10,
            headers={},
        )

    @patch('minibus.tracking_client.requests.get')
    def test_fetch_fleet_locations_upstream_error(self, mock_get):
        mock_get.return_value = MagicMock(ok=False, status_code=500, text='error')

        with self.assertRaises(MinibusTrackingError):
            fetch_fleet_locations()

    @patch('minibus.tracking_client.requests.get')
    def test_fetch_fleet_locations_timeout(self, mock_get):
        mock_get.side_effect = requests.Timeout('timed out')

        with self.assertRaises(MinibusTrackingError):
            fetch_fleet_locations()

    @patch('minibus.tracking_client.requests.get')
    @patch('minibus.tracking_client.MINIBUS_TRACKING_BASE_URL', 'https://example.test/publicapi')
    def test_fetch_vehicle_location_success(self, mock_get):
        mock_get.return_value = MagicMock(
            ok=True,
            status_code=200,
            json=lambda: {'id': '11010939', 'currentStopSequence': 10},
        )

        result = fetch_vehicle_location('11010939')

        self.assertEqual(result['id'], '11010939')
        mock_get.assert_called_once_with(
            'https://example.test/publicapi/locations/11010939',
            timeout=10,
            headers={},
        )

    @patch('minibus.tracking_client.requests.get')
    @patch('minibus.tracking_client.MINIBUS_TRACKING_PROXY_KEY', 'pi-proxy-secret')
    @patch(
        'minibus.tracking_client.MINIBUS_TRACKING_BASE_URL',
        'http://100.64.0.1:8080/publicapi',
    )
    def test_fetch_fleet_locations_sends_proxy_key_header(self, mock_get):
        mock_get.return_value = MagicMock(
            ok=True,
            status_code=200,
            json=lambda: [{'id': '11010939'}],
        )

        fetch_fleet_locations()

        mock_get.assert_called_once_with(
            'http://100.64.0.1:8080/publicapi/locations',
            timeout=10,
            headers={'X-Tracking-Proxy-Key': 'pi-proxy-secret'},
        )

    @patch('minibus.tracking_client.requests.get')
    def test_fetch_vehicle_location_not_found(self, mock_get):
        mock_get.return_value = MagicMock(ok=False, status_code=404, text='not found')

        with self.assertRaises(MinibusTrackingNotFoundError):
            fetch_vehicle_location('missing')


class ProxiedRequestTests(SimpleTestCase):
    """With a proxy configured, the auth and host headers must actually be sent.

    The no-proxy tests above cannot catch a dropped header: build_request
    returns {} without a proxy, so a client that ignores its headers argument
    and one that honours it send exactly the same thing. This bug reached a live
    proxy and returned 401 while every unit test passed.
    """

    @patch('minibus.tracking_client.requests.get')
    @patch('shared.upstream_proxy.UPSTREAM_PROXY_URL', 'http://10.0.0.1:8081')
    @patch('shared.upstream_proxy.UPSTREAM_PROXY_KEY', 'secret')
    def test_the_proxy_key_and_host_reach_requests(self, mock_get):
        mock_get.return_value = MagicMock(
            ok=True, status_code=200, json=lambda: [], text='',
        )
        fetch_fleet_locations()

        sent = mock_get.call_args.kwargs['headers']
        self.assertEqual(sent['X-Tracking-Proxy-Key'], 'secret')
        self.assertEqual(
            sent['X-Upstream-Host'], 'https://pdl.elevensystems.pt',
        )

    @patch('minibus.tracking_client.requests.get')
    @patch('shared.upstream_proxy.UPSTREAM_PROXY_URL', 'http://10.0.0.1:8081')
    @patch('shared.upstream_proxy.UPSTREAM_PROXY_KEY', 'secret')
    def test_the_full_upstream_path_is_preserved_through_the_proxy(self, mock_get):
        mock_get.return_value = MagicMock(
            ok=True, status_code=200, json=lambda: {}, text='',
        )
        fetch_vehicle_location('11010934')

        self.assertEqual(
            mock_get.call_args.args[0],
            'http://10.0.0.1:8081/publicapi/locations/11010934',
        )
