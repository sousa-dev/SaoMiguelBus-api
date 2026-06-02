"""Transit v3 API tests for directions, trips, and lines."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from transit.tests.fixtures import ensure_transit_fixtures


class TransitV3DirectionsAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.island, self.trip, self.line = ensure_transit_fixtures()
        self.headers = {'HTTP_X_ISLAND': 'sao-miguel'}

    def test_directions_requires_origin_destination(self):
        response = self.client.get('/api/v3/transit/directions', **self.headers)
        self.assertEqual(response.status_code, 400)

    @override_settings(GOOGLE_MAPS_API_KEY='test-key')
    @patch('transit.services.directions_v3.requests.get')
    def test_directions_happy_path(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {'routes': [{'legs': []}]}

        response = self.client.get(
            '/api/v3/transit/directions',
            {
                'origin': 'Ponta Delgada',
                'destination': 'Ribeira Grande',
                'day': 'weekday',
                'start': '08:00',
                'session_id': 'test-session',
            },
            **self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('routes', response.json())

    def test_directions_maps_disabled(self):
        self.island.feature_flags = {'maps': False, 'transit': True}
        self.island.save(update_fields=['feature_flags'])
        response = self.client.get(
            '/api/v3/transit/directions',
            {'origin': 'A', 'destination': 'B', 'session_id': 's1'},
            **self.headers,
        )
        self.assertEqual(response.status_code, 400)


class TransitV3TripLineAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.island, self.trip, self.line = ensure_transit_fixtures()
        self.headers = {'HTTP_X_ISLAND': 'sao-miguel'}

    def test_trip_detail(self):
        response = self.client.get(
            f'/api/v3/transit/trips/{self.trip.id}',
            **self.headers,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['id'], self.trip.id)
        self.assertEqual(len(body['stops']), 2)

    def test_trip_not_found(self):
        response = self.client.get('/api/v3/transit/trips/999999', **self.headers)
        self.assertEqual(response.status_code, 404)

    def test_line_detail(self):
        response = self.client.get(
            f'/api/v3/transit/lines/{self.line.code}',
            **self.headers,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['code'], self.line.code)
        self.assertGreaterEqual(len(body['trips']), 1)

    def test_line_not_found(self):
        response = self.client.get('/api/v3/transit/lines/NOPE', **self.headers)
        self.assertEqual(response.status_code, 404)
