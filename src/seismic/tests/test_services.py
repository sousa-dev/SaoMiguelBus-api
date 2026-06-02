"""EMSC sync service tests."""

from datetime import datetime, timezone as dt_timezone
from unittest.mock import MagicMock, patch

from django.test import TestCase

from seismic.models import SeismicEvent
from seismic.services import _parse_feature, sync_events_for_island
from tenancy.services import get_or_create_default_island


SAMPLE_FEATURES = {
    'type': 'FeatureCollection',
    'features': [
        {
            'type': 'Feature',
            'id': '20260601_0000001',
            'properties': {
                'unid': '20260601_0000001',
                'mag': 3.4,
                'time': '2026-06-01T10:00:00.0Z',
                'lat': 37.8,
                'lon': -25.5,
                'depth': 12.0,
                'flynn_region': 'AZORES REGION',
            },
            'geometry': {'type': 'Point', 'coordinates': [-25.5, 37.8, 12.0]},
        },
        {
            'type': 'Feature',
            'properties': {
                'mag': 2.0,
                'time': '2026-06-01T11:00:00.0Z',
                'lat': 37.7,
                'lon': -25.4,
            },
        },
    ],
}


class SeismicServicesTestCase(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        self.island.feature_flags = {**self.island.feature_flags, 'seismic': True}
        self.island.save()

    def test_parse_feature_requires_unid(self):
        self.assertIsNone(_parse_feature({'properties': {'mag': 1.0, 'lat': 1, 'lon': 2}}))

    def test_parse_feature_maps_fields(self):
        row = _parse_feature(SAMPLE_FEATURES['features'][0])
        assert row is not None
        self.assertEqual(row['emsc_id'], '20260601_0000001')
        self.assertEqual(row['magnitude'], 3.4)
        self.assertEqual(row['region'], 'AZORES REGION')

    @patch('seismic.services.requests.get')
    def test_sync_events_upserts_without_duplicates(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"features": []}'
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = SAMPLE_FEATURES
        mock_get.return_value = mock_response

        first = sync_events_for_island(self.island)
        self.assertEqual(first['created'], 1)
        self.assertEqual(first['skipped'], 0)
        self.assertEqual(SeismicEvent.objects.count(), 1)

        second = sync_events_for_island(self.island)
        self.assertEqual(second['created'], 0)
        self.assertEqual(second['updated'], 1)
        self.assertEqual(SeismicEvent.objects.count(), 1)

    @patch('seismic.services.requests.get')
    def test_sync_empty_features(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"features": []}'
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {'features': []}
        mock_get.return_value = mock_response

        counts = sync_events_for_island(self.island)
        self.assertEqual(counts['created'], 0)
        self.assertEqual(SeismicEvent.objects.count(), 0)

    @patch('seismic.services.requests.get')
    def test_sync_emsc_nodata_204(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.content = b''
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        counts = sync_events_for_island(self.island)
        self.assertEqual(counts['created'], 0)
        self.assertEqual(SeismicEvent.objects.count(), 0)
