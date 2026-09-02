from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import TestCase

from azoresbus.models import ExternalJourney
from tenancy.services import get_or_create_default_island
from transit.models import DATASET_AZORESBUS, Line, Operator, Trip

LIST = [
    {'id': '11', 'position': {'lat': 37.8, 'lon': -25.5}},
    {'id': '22', 'position': {'lat': 37.8, 'lon': -25.5}},
]


def _detail(vehicle_id, journey_id):
    return {
        'id': vehicle_id,
        'position': {'lat': 37.8, 'lon': -25.5},
        'route': {'id': '9', 'nameShort': '110', 'name': 'PDL - RG', 'color': '2D59A9'},
        'journey': {'id': journey_id, 'name': '09:10 >> 10:40', 'circulations': []},
    }


class ReportLiveJourneyMatchTests(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        operator = Operator.objects.create(island=self.island, name='AzoresBus')
        line = Line.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, operator=operator, code='110',
        )
        trip = Trip.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, line=line,
            calendar=None, service=None, source=Trip.SOURCE_OPERATOR,
        )
        ExternalJourney.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS,
            external_id='1861', route_ext_id='9', direction=0, trip=trip,
        )

    @patch('azoresbus.tracking_client.requests.get')
    def test_counts_matched_and_unmatched_vehicles(self, mock_get):
        def _response(url, **_kwargs):
            stripped = url.rstrip('/')
            if stripped.endswith('/11'):
                payload = _detail('11', '1861')
            elif stripped.endswith('/22'):
                payload = _detail('22', '9999')
            else:
                payload = LIST
            return MagicMock(ok=True, status_code=200, json=lambda: payload, text='')
        mock_get.side_effect = _response

        out = StringIO()
        call_command('report_live_journey_match', island_key='sao-miguel', stdout=out)
        text = out.getvalue()
        self.assertIn('fleet=2 matched=1 unmatched=1 failed=0 known_journeys=1', text)
        self.assertIn("unmatched vehicle=22 journey='9999' line=110", text)
