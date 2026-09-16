"""Tests for `GET /api/v3/ai/stops`."""

from __future__ import annotations

from django.test import TestCase
from django.core.cache import cache
from rest_framework.test import APIClient

from tenancy.services import for_island
from transit.models import Stop
from transit.tests.fixtures import ensure_transit_fixtures


class AIStopsTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.island, self.trip, self.line = ensure_transit_fixtures()
        with for_island(self.island):
            Stop.objects.get_or_create(
                island=self.island,
                cleaned_name='furnas',
                defaults={'name': 'Furnas', 'latitude': 37.7654, 'longitude': -25.3208},
            )
            Stop.objects.get_or_create(
                island=self.island,
                cleaned_name='aeroporto',
                defaults={'name': 'Aeroporto', 'latitude': 37.7412, 'longitude': -25.6975},
            )

    def test_exact_match(self):
        response = self.client.get('/api/v3/ai/stops', {'q': 'Furnas'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        names = [stop['name'] for stop in body['stops']]
        self.assertIn('Furnas', names)
        top = body['stops'][0]
        self.assertEqual(top['name'], 'Furnas')
        self.assertEqual(top['score'], 1.0)
        self.assertIn('latitude', top)
        self.assertIn('longitude', top)

    def test_prefix_match(self):
        response = self.client.get('/api/v3/ai/stops', {'q': 'Ponta Del'})
        self.assertEqual(response.status_code, 200)
        names = [stop['name'] for stop in response.json()['stops']]
        self.assertIn('Ponta Delgada', names)

    def test_fuzzy_typo_match(self):
        response = self.client.get('/api/v3/ai/stops', {'q': 'Furnaz'})
        self.assertEqual(response.status_code, 200)
        names = [stop['name'] for stop in response.json()['stops']]
        self.assertIn('Furnas', names)

    def test_alias_match_airport(self):
        response = self.client.get('/api/v3/ai/stops', {'q': 'airport'})
        self.assertEqual(response.status_code, 200)
        names = [stop['name'] for stop in response.json()['stops']]
        self.assertIn('Aeroporto', names)

    def test_no_query_returns_empty_list(self):
        response = self.client.get('/api/v3/ai/stops')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['stops'], [])
        self.assertEqual(body['query'], '')

    def test_limit_is_respected(self):
        response = self.client.get('/api/v3/ai/stops', {'q': 'a', 'limit': '2'})
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.json()['stops']), 2)
