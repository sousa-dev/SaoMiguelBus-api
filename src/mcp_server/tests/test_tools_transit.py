"""Tests for the transit MCP tools -- call the sync `*_impl` functions directly,
inside `with for_island(island):`, exactly like the bridge does in a worker thread.
"""

from __future__ import annotations

from django.test import TestCase

from tenancy.services import for_island
from transit.models import ServicePattern
from transit.tests.fixtures import ensure_transit_fixtures
from mcp_server.tools.transit import (
    _journeys_impl,
    _line_impl,
    _search_impl,
    _stop_detail_impl,
    _stops_impl,
    _tariffs_impl,
    _trip_impl,
)


class TransitToolsTestCase(TestCase):
    def setUp(self):
        self.island, self.trip, self.line = ensure_transit_fixtures()
        with for_island(self.island):
            service, _ = ServicePattern.objects.get_or_create(
                island=self.island, key='mcp-test-weekdays',
                defaults={day: True for day in ServicePattern.WEEKDAY_FIELDS[:5]},
            )
            self.trip.service = service
            self.trip.save(update_fields=['service'])

    def test_list_stops_returns_both_stops(self):
        with for_island(self.island):
            result = _stops_impl(self.island)
        names = {stop['name'] for stop in result['stops']}
        self.assertEqual(names, {'Ponta Delgada', 'Ribeira Grande'})

    def test_list_stops_query_filters(self):
        with for_island(self.island):
            result = _stops_impl(self.island, query='ribeira')
        self.assertEqual([s['name'] for s in result['stops']], ['Ribeira Grande'])

    def test_stop_detail_known_stop(self):
        from transit.models import Stop
        with for_island(self.island):
            origin = Stop.objects.get(island=self.island, cleaned_name='ponta delgada')
            result = _stop_detail_impl(self.island, origin.id, day='weekday', start='00:00')
        self.assertNotIn('error', result)

    def test_stop_detail_unknown_stop_is_not_found(self):
        with for_island(self.island):
            result = _stop_detail_impl(self.island, 999999)
        self.assertEqual(result['error']['code'], 'not_found')

    def test_search_known_pair_returns_a_result(self):
        with for_island(self.island):
            result = _search_impl(
                self.island, 'Ponta Delgada', 'Ribeira Grande', day='weekday', start='00:00',
            )
        self.assertEqual(len(result['results']), 1)
        self.assertEqual(result['results'][0]['start'], '08h30')

    def test_search_unresolved_stop_returns_empty_results_not_an_error(self):
        with for_island(self.island):
            result = _search_impl(self.island, 'Nowhere At All', 'Ribeira Grande')
        self.assertEqual(result['results'], [])

    def test_search_invalid_day_raises_value_error(self):
        with for_island(self.island):
            with self.assertRaises(ValueError):
                _search_impl(self.island, 'Ponta Delgada', 'Ribeira Grande', day='someday')

    def test_search_invalid_start_raises_value_error(self):
        with for_island(self.island):
            with self.assertRaises(ValueError):
                _search_impl(
                    self.island, 'Ponta Delgada', 'Ribeira Grande', start='25:99',
                )

    def test_journeys_known_pair(self):
        with for_island(self.island):
            result = _journeys_impl(
                self.island, 'Ponta Delgada', 'Ribeira Grande',
                day='2026-09-15', start='00:00', max_transfers=0,
            )
        self.assertGreaterEqual(len(result['journeys']), 1)

    def test_trip_known_id(self):
        with for_island(self.island):
            result = _trip_impl(self.island, self.trip.id)
        self.assertEqual(result['route'], self.line.code)

    def test_trip_unknown_id_is_not_found(self):
        with for_island(self.island):
            result = _trip_impl(self.island, 999999)
        self.assertEqual(result['error']['code'], 'not_found')

    def test_line_known_code(self):
        with for_island(self.island):
            result = _line_impl(self.island, self.line.code)
        self.assertEqual(result['code'], self.line.code)

    def test_line_unknown_code_is_not_found(self):
        with for_island(self.island):
            result = _line_impl(self.island, 'NOPE')
        self.assertEqual(result['error']['code'], 'not_found')

    def test_tariffs_without_snapshot_is_not_found(self):
        with for_island(self.island):
            result = _tariffs_impl(self.island)
        self.assertEqual(result['error']['code'], 'not_found')
