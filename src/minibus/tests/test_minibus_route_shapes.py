"""Tests for minibus route shape harvest."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from minibus.models import MinibusLine
from minibus.services import seed_catalog
from minibus.services_route_shapes import (
    decode_polyline,
    harvest_route_shapes,
    line_has_shape,
    pick_fleet_vehicle_ids_by_line,
    resolve_line_code_from_vehicle,
)
from minibus.tracking_client import MinibusTrackingError
from tenancy.services import get_or_create_default_island


FLEET_FIXTURE = [
    {'id': '11010933', 'color': '00964C', 'status': 'ontime'},
    {'id': '11010943', 'color': 'F6BC1C', 'status': 'ontime'},
    {'id': '11010936', 'color': '2D3276', 'status': 'ontime'},
    {'id': '11010944', 'color': 'EC6E00', 'status': 'ontime'},
]

DETAIL_BY_ID = {
    '11010933': {
        'id': '11010933',
        'journey': {'shape': 'uxieF~tt{CLMRA', 'direction': 0, 'id': '2'},
        'route': {'nameShort': 'B'},
    },
    '11010943': {
        'id': '11010943',
        'journey': {'shape': 'uxieF~tt{CLMRA', 'direction': 0, 'id': '1'},
        'route': {'nameShort': 'A'},
    },
    '11010936': {
        'id': '11010936',
        'journey': {'shape': 'uxieF~tt{CLMRA', 'direction': 0, 'id': '3'},
        'route': {'nameShort': 'C'},
    },
    '11010944': {
        'id': '11010944',
        'journey': {'shape': 'uxieF~tt{CLMRA', 'direction': 0, 'id': '5'},
        'route': {'nameShort': 'D'},
    },
}


class RouteShapeHelpersTestCase(TestCase):
    def test_resolve_line_code_from_color(self):
        self.assertEqual(resolve_line_code_from_vehicle({'color': '00964C'}), 'B')

    def test_resolve_line_code_from_route_name_short(self):
        self.assertEqual(resolve_line_code_from_vehicle({'route': {'nameShort': 'C'}}), 'C')

    def test_decode_polyline_returns_points(self):
        coords = decode_polyline('uxieF~tt{CLMRA')
        self.assertGreaterEqual(len(coords), 2)

    def test_pick_fleet_vehicle_ids_by_line_dedupes(self):
        fleet = [
            {'id': '1', 'color': '00964C'},
            {'id': '2', 'color': '00964C'},
        ]
        mapping = pick_fleet_vehicle_ids_by_line(fleet)
        self.assertEqual(mapping, {'B': '1'})


@patch('minibus.services_route_shapes.fetch_vehicle_location')
@patch('minibus.services_route_shapes.fetch_fleet_locations')
class HarvestRouteShapesTestCase(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        flags = dict(self.island.feature_flags or {})
        flags['minibus'] = True
        self.island.feature_flags = flags
        self.island.save(update_fields=['feature_flags'])
        seed_catalog(self.island)

    def test_harvests_all_lines(self, mock_fleet, mock_vehicle):
        mock_fleet.return_value = FLEET_FIXTURE
        mock_vehicle.side_effect = lambda tracking_id: DETAIL_BY_ID[tracking_id]

        report = harvest_route_shapes(self.island)

        self.assertEqual(report['status'], 'ok')
        self.assertEqual(set(report['harvested']), {'A', 'B', 'C', 'D'})
        self.assertEqual(report['missing'], [])
        line_b = MinibusLine.objects.get(island=self.island, code='B')
        self.assertTrue(line_has_shape(line_b))
        self.assertEqual(line_b.route_shapes[0]['source_vehicle_id'], '11010933')

    def test_partial_fleet_leaves_missing_lines(self, mock_fleet, mock_vehicle):
        mock_fleet.return_value = FLEET_FIXTURE[:2]
        mock_vehicle.side_effect = lambda tracking_id: DETAIL_BY_ID[tracking_id]

        report = harvest_route_shapes(self.island)

        self.assertEqual(set(report['harvested']), {'A', 'B'})
        self.assertEqual(set(report['missing']), {'C', 'D'})

    def test_skips_lines_with_existing_shape(self, mock_fleet, mock_vehicle):
        line_a = MinibusLine.objects.get(island=self.island, code='A')
        line_a.route_shapes = [
            {
                'direction': 0,
                'encoded_polyline': 'uxieF~tt{CLMRA',
                'journey_id': '1',
                'source_vehicle_id': 'saved',
                'captured_at': '2026-01-01T00:00:00+00:00',
            },
        ]
        line_a.save(update_fields=['route_shapes'])

        mock_fleet.return_value = FLEET_FIXTURE
        mock_vehicle.side_effect = lambda tracking_id: DETAIL_BY_ID[tracking_id]

        report = harvest_route_shapes(self.island)

        self.assertNotIn('A', report['harvested'])
        line_a.refresh_from_db()
        self.assertEqual(line_a.route_shapes[0]['source_vehicle_id'], 'saved')

    def test_upstream_fleet_error_returns_partial_report(self, mock_fleet, mock_vehicle):
        mock_fleet.side_effect = MinibusTrackingError('upstream down')

        report = harvest_route_shapes(self.island)

        self.assertEqual(report['status'], 'error')
        self.assertEqual(report['reason'], 'tracking_unavailable')
        self.assertEqual(set(report['missing']), {'A', 'B', 'C', 'D'})
        mock_vehicle.assert_not_called()

    def test_missing_shape_in_detail_is_skipped(self, mock_fleet, mock_vehicle):
        mock_fleet.return_value = [{'id': '11010933', 'color': '00964C'}]
        mock_vehicle.return_value = {'id': '11010933', 'journey': {}, 'route': {'nameShort': 'B'}}

        report = harvest_route_shapes(self.island)

        self.assertEqual(report['harvested'], [])
        self.assertIn('B', report['skipped'])


class HarvestRouteShapesDisabledTestCase(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        self.island.feature_flags = {**(self.island.feature_flags or {}), 'minibus': False}
        self.island.save(update_fields=['feature_flags'])
        seed_catalog(self.island)

    @patch('minibus.services_route_shapes.fetch_fleet_locations')
    def test_noop_when_minibus_disabled(self, mock_fleet):
        report = harvest_route_shapes(self.island)

        self.assertEqual(report['status'], 'skipped')
        mock_fleet.assert_not_called()
