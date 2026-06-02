"""Trails open-data sync service tests."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from trails.models import POI, Trail
from trails.services import (
    feature_in_island,
    parse_poi_feature,
    parse_trail_feature,
    sync_open_data_for_island,
    sync_pois_for_island,
    sync_trails_for_island,
)
from tenancy.services import get_or_create_default_island

SAMPLE_TRAIL_COLLECTION = {
    'type': 'FeatureCollection',
    'features': [
        {
            'type': 'Feature',
            'id': 'trail-1',
            'properties': {
                'id': 'trail-1',
                'nome': 'Trilho da Lagoa',
                'dificuldade': 'facil',
            },
            'geometry': {
                'type': 'LineString',
                'coordinates': [
                    [-25.50, 37.78],
                    [-25.49, 37.79],
                ],
            },
        },
        {
            'type': 'Feature',
            'properties': {'id': 'far-away'},
            'geometry': {
                'type': 'LineString',
                'coordinates': [[0.0, 0.0], [0.1, 0.1]],
            },
        },
        {
            'type': 'Feature',
            'properties': {},
            'geometry': {
                'type': 'LineString',
                'coordinates': [[-25.50, 37.78], [-25.49, 37.79]],
            },
        },
    ],
}

SAMPLE_POI_COLLECTION = {
    'type': 'FeatureCollection',
    'features': [
        {
            'type': 'Feature',
            'properties': {'id': 'poi-1', 'nome': 'Miradouro', 'tipo': 'Miradouro'},
            'geometry': {'type': 'Point', 'coordinates': [-25.50, 37.78]},
        },
    ],
}


class TrailsServicesTestCase(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        self.island.feature_flags = {**self.island.feature_flags, 'trails': True}
        self.island.save()

    def test_parse_trail_feature_maps_fields(self):
        row = parse_trail_feature(SAMPLE_TRAIL_COLLECTION['features'][0])
        assert row is not None
        self.assertEqual(row['source_ref'], 'trail-1')
        self.assertEqual(row['name'], 'Trilho da Lagoa')
        self.assertEqual(row['difficulty'], 'easy')
        self.assertIsNotNone(row['distance_km'])

    def test_parse_trail_feature_requires_source_ref(self):
        self.assertIsNone(parse_trail_feature(SAMPLE_TRAIL_COLLECTION['features'][2]))

    def test_parse_poi_feature_maps_fields(self):
        row = parse_poi_feature(SAMPLE_POI_COLLECTION['features'][0])
        assert row is not None
        self.assertEqual(row['source_ref'], 'poi-1')
        self.assertEqual(row['category'], 'Miradouro')

    def test_feature_in_island_bbox(self):
        self.assertTrue(
            feature_in_island(SAMPLE_TRAIL_COLLECTION['features'][0], self.island),
        )
        self.assertFalse(
            feature_in_island(SAMPLE_TRAIL_COLLECTION['features'][1], self.island),
        )

    def test_sync_trails_upserts_without_duplicates(self):
        first = sync_trails_for_island(self.island, collection=SAMPLE_TRAIL_COLLECTION)
        self.assertEqual(first['created'], 1)
        self.assertEqual(first['skipped'], 2)
        self.assertEqual(Trail.objects.count(), 1)

        second = sync_trails_for_island(self.island, collection=SAMPLE_TRAIL_COLLECTION)
        self.assertEqual(second['created'], 0)
        self.assertEqual(second['updated'], 1)
        self.assertEqual(Trail.objects.count(), 1)

    def test_sync_pois_creates_rows(self):
        counts = sync_pois_for_island(self.island, collection=SAMPLE_POI_COLLECTION)
        self.assertEqual(counts['created'], 1)
        self.assertEqual(POI.objects.count(), 1)

    def test_sync_empty_collection(self):
        empty = {'type': 'FeatureCollection', 'features': []}
        counts = sync_trails_for_island(self.island, collection=empty)
        self.assertEqual(counts['created'], 0)
        self.assertEqual(Trail.objects.count(), 0)

    @patch('trails.services.fetch_dataset_geojson')
    @patch('trails.visitazores_sync.sync_visitazores_trails_for_island')
    def test_sync_open_data_for_island(self, mock_trails, mock_fetch):
        mock_trails.return_value = {'created': 1, 'updated': 0, 'skipped': 0}
        mock_fetch.return_value = SAMPLE_POI_COLLECTION
        totals = sync_open_data_for_island(self.island)
        self.assertEqual(totals['trails_created'], 1)
        self.assertEqual(totals['pois_created'], 1)

    @patch('trails.services.fetch_udata_dataset')
    def test_fetch_dataset_geojson_http_error(self, mock_dataset):
        mock_dataset.side_effect = Exception('503')
        with self.assertRaises(Exception):
            from trails.services import fetch_dataset_geojson

            fetch_dataset_geojson('test-dataset')
