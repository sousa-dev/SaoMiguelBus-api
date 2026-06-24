"""Deploy bootstrap minibus route shape harvest command tests."""

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from minibus.models import MinibusLine
from minibus.services import seed_catalog
from tenancy.services import get_or_create_default_island


class BootstrapMinibusRouteShapesTestCase(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        self.island.is_live = True
        self.island.feature_flags = {
            **(self.island.feature_flags or {}),
            'minibus': True,
        }
        self.island.save()
        seed_catalog(self.island)

    @patch('minibus.tasks.harvest_route_shapes_task')
    def test_bootstrap_queues_when_shapes_missing(self, mock_task):
        mock_task.delay.return_value.id = 'task-123'
        out = StringIO()
        call_command('bootstrap_minibus_route_shapes', island='sao-miguel', stdout=out)
        mock_task.delay.assert_called_once_with(island_key='sao-miguel')
        self.assertIn('Queued minibus route shape harvest', out.getvalue())

    @patch('minibus.tasks.harvest_route_shapes_task')
    def test_bootstrap_skips_when_all_shapes_present(self, mock_task):
        shape = {
            'direction': 0,
            'encoded_polyline': 'uxieF~tt{CLMRA',
            'journey_id': '1',
            'source_vehicle_id': 'saved',
            'captured_at': '2026-01-01T00:00:00+00:00',
        }
        for line in MinibusLine.objects.filter(island=self.island):
            line.route_shapes = [shape]
            line.save(update_fields=['route_shapes'])

        out = StringIO()
        call_command('bootstrap_minibus_route_shapes', island='sao-miguel', stdout=out)
        mock_task.delay.assert_not_called()
        self.assertIn('No minibus route shape harvest tasks queued', out.getvalue())

    @patch('minibus.tasks.harvest_route_shapes_task')
    def test_bootstrap_noop_when_minibus_disabled(self, mock_task):
        self.island.feature_flags = {**(self.island.feature_flags or {}), 'minibus': False}
        self.island.save(update_fields=['feature_flags'])
        out = StringIO()
        call_command('bootstrap_minibus_route_shapes', island='sao-miguel', stdout=out)
        mock_task.delay.assert_not_called()
        self.assertIn('No minibus route shape harvest tasks queued', out.getvalue())
