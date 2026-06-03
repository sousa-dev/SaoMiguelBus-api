"""API tests for the v3 offline-bundle and version endpoints."""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from transit.models import Stop
from transit.tests.fixtures import ensure_transit_fixtures


class OfflineBundleAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.island, self.trip, self.line = ensure_transit_fixtures()
        self.headers = {'HTTP_X_ISLAND': 'sao-miguel'}

    def test_version_falls_back_to_default_island(self):
        response = self.client.get('/api/v3/transit/offline-bundle/version')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['island'], 'sao-miguel')

    def test_version_endpoint(self):
        response = self.client.get('/api/v3/transit/offline-bundle/version', **self.headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['island'], 'sao-miguel')
        self.assertTrue(body['version'])

    def test_bundle_endpoint_shape_and_etag(self):
        response = self.client.get('/api/v3/transit/offline-bundle', **self.headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        for key in ('version', 'island', 'stops', 'routes', 'holidays', 'infos', 'counts'):
            self.assertIn(key, body)
        self.assertEqual(response['ETag'], f'"{body["version"]}"')

    def test_conditional_get_returns_304(self):
        version = self.client.get(
            '/api/v3/transit/offline-bundle/version', **self.headers
        ).json()['version']
        response = self.client.get(
            '/api/v3/transit/offline-bundle',
            HTTP_IF_NONE_MATCH=f'"{version}"',
            **self.headers,
        )
        self.assertEqual(response.status_code, 304)

    def test_version_changes_after_data_edit(self):
        v1 = self.client.get(
            '/api/v3/transit/offline-bundle/version', **self.headers
        ).json()['version']
        Stop.objects.create(
            island=self.island,
            name='Lagoa',
            cleaned_name='lagoa',
            latitude=37.74,
            longitude=-25.57,
        )
        v2 = self.client.get(
            '/api/v3/transit/offline-bundle/version', **self.headers
        ).json()['version']
        self.assertNotEqual(v1, v2)

        # Stale ETag no longer matches → full payload returned.
        response = self.client.get(
            '/api/v3/transit/offline-bundle',
            HTTP_IF_NONE_MATCH=f'"{v1}"',
            **self.headers,
        )
        self.assertEqual(response.status_code, 200)
