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
