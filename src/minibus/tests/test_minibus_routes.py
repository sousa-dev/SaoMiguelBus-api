"""Mini Bus route-search (origin -> destination) tests."""

from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from minibus.services import (
    build_network_graph,
    load_network_stops,
    normalize_token,
    resolve_stop_refs,
    search_routes,
    seed_catalog,
)
from tenancy.services import get_or_create_default_island


class NetworkGraphTestCase(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.network = load_network_stops()
        cls.graph = build_network_graph(cls.network)

    def test_graph_has_every_stop_as_node(self):
        expected = sum(len(line['stops']) for line in self.network['lines'])
        self.assertEqual(len(self.graph.nodes), expected)

    def test_intra_line_edges_are_circular(self):
        line_a = next(l for l in self.network['lines'] if l['code'] == 'A')
        last = max(line_a['stops'], key=lambda s: s['sequence'])
        first = min(line_a['stops'], key=lambda s: s['sequence'])
        neighbours = [dst for dst, is_transfer in self.graph.edges[last['key']] if not is_transfer]
        self.assertIn(first['key'], neighbours)

    def test_transfer_edges_connect_shared_interchange_across_lines(self):
        # avenida-antero-de-quental is shared by lines A and D.
        a_node = next(
            k for k, n in self.graph.nodes.items()
            if n.interchange_key == 'avenida-antero-de-quental' and n.line_code == 'A'
        )
        transfers = [dst for dst, is_transfer in self.graph.edges[a_node] if is_transfer]
        self.assertTrue(transfers)
        self.assertTrue(all(self.graph.nodes[dst].line_code != 'A' for dst in transfers))


class ResolveStopRefsTestCase(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.graph = build_network_graph(load_network_stops())

    def test_normalize_token_strips_accents_and_punctuation(self):
        self.assertEqual(normalize_token('Praça Vasco da Gama'), 'praca-vasco-da-gama')

    def test_resolve_by_stop_key(self):
        self.assertEqual(resolve_stop_refs(self.graph, 'a-01'), ['a-01'])

    def test_resolve_by_name(self):
        keys = resolve_stop_refs(self.graph, 'Rua Teófilo Braga')
        self.assertIn('d-02', keys)

    def test_resolve_interchange_returns_all_lines(self):
        keys = resolve_stop_refs(self.graph, 'Praça Vasco da Gama')
        lines = {self.graph.nodes[k].line_code for k in keys}
        self.assertEqual(lines, {'B', 'C', 'D'})


class SearchRoutesTestCase(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.graph = build_network_graph(load_network_stops())

    def test_direct_journey_has_no_transfers(self):
        journeys = search_routes(self.graph, ['a-01'], ['a-08'])
        self.assertTrue(journeys)
        best = journeys[0]
        self.assertEqual(best['transfers'], 0)
        self.assertEqual(len(best['legs']), 1)
        self.assertEqual(best['legs'][0]['line_code'], 'A')
        self.assertEqual(best['legs'][0]['board']['key'], 'a-01')
        self.assertEqual(best['legs'][0]['alight']['key'], 'a-08')

    def test_cross_line_journey_requires_a_transfer(self):
        # a-01 is unique to line A; d-02 is unique to line D.
        journeys = search_routes(self.graph, ['a-01'], ['d-02'])
        self.assertTrue(journeys)
        best = journeys[0]
        self.assertGreaterEqual(best['transfers'], 1)
        self.assertEqual(len(best['legs']), best['transfers'] + 1)
        self.assertEqual(best['legs'][0]['line_code'], 'A')
        self.assertEqual(best['legs'][-1]['line_code'], 'D')
        self.assertEqual(best['legs'][-1]['alight']['key'], 'd-02')
        # transfer stop names are reported between legs
        self.assertEqual(len(best['transfer_stops']), best['transfers'])

    def test_legs_reserve_schedule_fields(self):
        journeys = search_routes(self.graph, ['a-01'], ['a-08'])
        leg = journeys[0]['legs'][0]
        self.assertIsNone(leg['departure_time'])
        self.assertIsNone(leg['arrival_time'])

    def test_results_are_capped_and_ranked_by_transfers(self):
        journeys = search_routes(self.graph, ['a-01'], ['d-02'], max_results=3)
        self.assertLessEqual(len(journeys), 3)
        transfers = [j['transfers'] for j in journeys]
        self.assertEqual(transfers, sorted(transfers))

    def test_unknown_stop_yields_no_journeys(self):
        self.assertEqual(search_routes(self.graph, [], ['a-08']), [])


class RouteSearchApiTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.island = get_or_create_default_island()
        flags = dict(self.island.feature_flags or {})
        flags['minibus'] = True
        self.island.feature_flags = flags
        self.island.save(update_fields=['feature_flags'])
        seed_catalog(self.island)

    def test_route_search_returns_enriched_journeys(self):
        response = self.client.get(
            '/api/v3/minibus/route?origin=a-01&destination=a-08&locale=pt',
            HTTP_X_ISLAND='sao-miguel',
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['origin']['matched'])
        self.assertTrue(body['journeys'])
        leg = body['journeys'][0]['legs'][0]
        self.assertEqual(leg['line_code'], 'A')
        self.assertEqual(leg['line_name'], 'Linha A — Amarela')
        self.assertEqual(leg['line_color'], '#fbc707')

    def test_route_search_requires_origin_and_destination(self):
        response = self.client.get(
            '/api/v3/minibus/route?origin=a-01',
            HTTP_X_ISLAND='sao-miguel',
        )
        self.assertEqual(response.status_code, 400)

    def test_route_search_unmatched_token_returns_empty_journeys(self):
        response = self.client.get(
            '/api/v3/minibus/route?origin=nowhere&destination=a-08',
            HTTP_X_ISLAND='sao-miguel',
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body['origin']['matched'])
        self.assertEqual(body['journeys'], [])
