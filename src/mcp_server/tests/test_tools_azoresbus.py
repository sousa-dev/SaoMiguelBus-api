"""Tests for the AzoresBus live-tracking MCP tools -- exception -> error-code
mapping must match `azoresbus/api_v3.py`'s REST views exactly.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from tenancy.services import for_island, get_or_create_default_island
from mcp_server.tools.azoresbus import (
    _arrivals_impl,
    _trips_impl,
    _vehicle_impl,
    _vehicles_impl,
)


class AzoresbusToolsTestCase(TestCase):
    def setUp(self):
        # Default island has no `feature_flags.azoresbus.trackingEnabled`, so
        # every tool call below hits the tracking-disabled branch first unless
        # a test explicitly mocks the underlying service to bypass it.
        self.island = get_or_create_default_island()

    def test_vehicles_tracking_disabled(self):
        with for_island(self.island):
            result = _vehicles_impl(self.island)
        self.assertEqual(result['error']['code'], 'tracking_disabled')

    def test_vehicle_tracking_disabled(self):
        with for_island(self.island):
            result = _vehicle_impl(self.island, 'bus-1')
        self.assertEqual(result['error']['code'], 'tracking_disabled')

    def test_arrivals_tracking_disabled(self):
        with for_island(self.island):
            result = _arrivals_impl(self.island, 1)
        self.assertEqual(result['error']['code'], 'tracking_disabled')

    def test_trips_live_tracking_disabled(self):
        with for_island(self.island):
            result = _trips_impl(self.island, [1, 2])
        self.assertEqual(result['error']['code'], 'tracking_disabled')

    def test_vehicle_not_found_maps_to_not_found(self):
        from azoresbus.tracking_client import AzoresbusVehicleNotFound
        with patch(
            'azoresbus.services_tracking.get_vehicle',
            side_effect=AzoresbusVehicleNotFound('missing'),
        ):
            with for_island(self.island):
                result = _vehicle_impl(self.island, 'ghost')
        self.assertEqual(result['error']['code'], 'not_found')

    def test_upstream_error_maps_to_tracking_unavailable(self):
        from azoresbus.tracking_client import AzoresbusTrackingError
        with patch(
            'azoresbus.services_tracking.get_fleet',
            side_effect=AzoresbusTrackingError('upstream down'),
        ):
            with for_island(self.island):
                result = _vehicles_impl(self.island)
        self.assertEqual(result['error']['code'], 'tracking_unavailable')

    def test_unexpected_exception_maps_to_internal_error(self):
        with patch(
            'azoresbus.services_tracking.get_fleet',
            side_effect=RuntimeError('boom'),
        ):
            with for_island(self.island):
                result = _vehicles_impl(self.island)
        self.assertEqual(result['error']['code'], 'internal_error')

    def test_trips_live_caps_to_five_ids(self):
        self.island.feature_flags = {
            **(self.island.feature_flags or {}),
            'azoresbus': {'trackingEnabled': True},
        }
        self.island.save(update_fields=['feature_flags'])
        with patch(
            'azoresbus.services_trip_live.live_for_trips', return_value=[],
        ) as live:
            with for_island(self.island):
                _trips_impl(self.island, [1, 2, 3, 4, 5, 6, 7])
        live.assert_called_once_with(self.island, [1, 2, 3, 4, 5])
