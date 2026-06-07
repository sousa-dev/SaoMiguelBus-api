"""Tests for agent documentation and OpenAPI endpoints."""

import json

from django.test import TestCase
from rest_framework.test import APIClient


class AgentDocsAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_index_lists_documents_and_openapi_links(self):
        response = self.client.get('/api/v3/agent-docs/')
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertIn('documents', body)
        self.assertIn('external_references', body)
        self.assertIn('openapi', body)

        slugs = {doc['slug'] for doc in body['documents']}
        self.assertIn('agents-md', slugs)
        self.assertIn('env-example', slugs)

        self.assertIn('/api/schema/', body['openapi']['schema_url'])
        self.assertIn('/api/docs/', body['openapi']['swagger_ui_url'])

    def test_detail_returns_agents_md(self):
        response = self.client.get('/api/v3/agent-docs/agents-md')
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(body['slug'], 'agents-md')
        self.assertEqual(body['format'], 'markdown')
        self.assertIn('São Miguel Bus API', body['content'])
        self.assertGreater(body['size_bytes'], 0)

    def test_detail_raw_format(self):
        response = self.client.get('/api/v3/agent-docs/readme?raw=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain; charset=utf-8')
        self.assertIn('São Miguel Bus API', response.content.decode())

    def test_unknown_slug_404(self):
        response = self.client.get('/api/v3/agent-docs/does-not-exist')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['error']['code'], 'not_found')


class OpenAPIDocsTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_openapi_schema(self):
        response = self.client.get(
            '/api/schema/',
            HTTP_ACCEPT='application/vnd.oai.openapi+json',
        )
        self.assertEqual(response.status_code, 200)
        schema = json.loads(response.content)
        self.assertIn('openapi', schema)

    def test_swagger_ui(self):
        response = self.client.get('/api/docs/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/html', response['Content-Type'])

    def test_redoc_ui(self):
        response = self.client.get('/api/docs/redoc/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/html', response['Content-Type'])
