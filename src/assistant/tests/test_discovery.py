"""Tests for the root-level self-description files: `/llms.txt`,
`/llms-full.txt`, `/robots.txt`, `/openapi.json`."""

from __future__ import annotations

import json

from django.test import TestCase
from rest_framework.test import APIClient

from transit.tests.fixtures import ensure_transit_fixtures


class LlmsTxtTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        ensure_transit_fixtures()

    def test_llms_txt_200_text_plain_with_ai_endpoint_and_island_name(self):
        response = self.client.get('/llms.txt')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain; charset=utf-8')
        self.assertIn('public, max-age=3600', response['Cache-Control'])

        body = response.content.decode()
        self.assertIn('/api/v3/ai/journeys', body)
        self.assertIn('/api/v3/ai/stops', body)
        self.assertIn('São Miguel', body)
        self.assertIn('## How to get bus times', body)
        self.assertIn('## Docs', body)

    def test_llms_full_txt_includes_quickstart_and_endpoint_reference(self):
        response = self.client.get('/llms-full.txt')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain; charset=utf-8')
        body = response.content.decode()
        self.assertIn('## How to get bus times', body)
        self.assertIn('## Full endpoint reference', body)
        self.assertIn('/api/v3/ai/journeys', body)
        self.assertIn('/api/v3/transit/journeys', body)


class RobotsTxtTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_robots_txt(self):
        response = self.client.get('/robots.txt')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain; charset=utf-8')
        body = response.content.decode()
        self.assertIn('User-agent: *', body)
        self.assertIn('Allow: /llms.txt', body)
        self.assertIn('Allow: /api/v3/ai/', body)
        self.assertIn('Disallow: /dashboard/', body)


class OpenAPIJSONTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_openapi_json_is_valid_json_with_ai_journeys_path(self):
        response = self.client.get('/openapi.json')
        self.assertEqual(response.status_code, 200)
        schema = json.loads(response.content)
        self.assertIn('openapi', schema)
        self.assertIn('/api/v3/ai/journeys', schema['paths'])
        self.assertIn('/api/v3/ai/stops', schema['paths'])
