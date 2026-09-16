"""Tests for the agent-docs MCP resources."""

from __future__ import annotations

import json

from django.test import SimpleTestCase

from mcp_server.resources import document_resource, documents_resource, guide_resource


class ResourcesTestCase(SimpleTestCase):
    def test_documents_index_lists_agents_md(self):
        index = json.loads(documents_resource())
        slugs = {doc['slug'] for doc in index}
        self.assertIn('agents-md', slugs)

    def test_document_reads_agents_md_content(self):
        content = document_resource('agents-md')
        self.assertIn('São Miguel Bus API', content)

    def test_unknown_document_slug_is_reported_not_raised(self):
        content = document_resource('does-not-exist')
        self.assertIn('Unknown document', content)

    def test_guide_mentions_transit_journeys(self):
        self.assertIn('transit_journeys', guide_resource())
