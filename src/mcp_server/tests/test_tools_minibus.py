"""Tests for the minibus MCP tools."""

from __future__ import annotations

from django.test import TestCase

from minibus.models import MinibusLine
from minibus.services import seed_catalog
from tenancy.services import for_island, get_or_create_default_island
from mcp_server.tools.minibus import _line_impl, _lines_impl, _route_impl


class MinibusToolsTestCase(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        with for_island(self.island):
            seed_catalog(self.island)

    def test_lines_returns_seeded_lines(self):
        with for_island(self.island):
            result = _lines_impl(self.island)
        self.assertEqual(len(result['lines']), 4)

    def test_line_known_slug(self):
        with for_island(self.island):
            line = MinibusLine.objects.filter(island=self.island).first()
            result = _line_impl(self.island, line.slug)
        self.assertNotIn('error', result)
        self.assertEqual(result['code'], line.code)

    def test_line_unknown_slug_is_not_found(self):
        with for_island(self.island):
            result = _line_impl(self.island, 'does-not-exist')
        self.assertEqual(result['error']['code'], 'not_found')

    def test_route_search_runs_without_error(self):
        with for_island(self.island):
            result = _route_impl(self.island, 'Ponta Delgada', 'Ponta Delgada')
        self.assertNotIn('error', result)
