"""02 §6: fare TABLES, never a computed fare.

Storage stays schemaless because all 148 `fareUnits` values are human-readable
band labels ("0 a 5", "6 a 7", "8") and the category/group/tariff nesting is the
operator's editorial structure, which will change without warning.

`fareUnitType: "km"` is not a price calculator: nothing in /api/stops, the
journeys or tariffs.json gives kilometres between two stops, so no caller can
answer "what will THIS ride cost?" (98 §4 gap "Fare distance").
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase
from rest_framework.test import APIClient

from azoresbus.models import TariffSnapshot
from azoresbus.services_tariffs import serialize_tariffs, store_snapshot
from tenancy.services import for_island, get_or_create_default_island


HEADERS = {'HTTP_X_ISLAND': 'sao-miguel'}

PAYLOAD = {
    'date': '2026-09-01',
    'comment': 'A aquisição do cartão do passe terá um custo de 6€.',
    'categories': [
        {
            'name': 'Passes Mensais',
            'groups': [
                {
                    'tariffs': [
                        {
                            'name': 'Mensal',
                            'fareUnitType': 'km',
                            'comment': 'Passe mensal',
                            'prices': [
                                {'fareUnits': '0 a 5', 'price': 31.75},
                                {'fareUnits': '6 a 7', 'price': 36.90},
                                {'fareUnits': '8', 'price': 40.00},
                            ],
                        },
                        {'name': 'Ex-Combatente', 'prices': [{'price': 0.0}]},
                    ],
                },
            ],
        },
    ],
    'infos': [{'text': 'Mais informação', 'url': 'https://azoresbus.pt/x.pdf'}],
}

HEADERS_UPSTREAM = {
    'ETag': '"80d474f2e024dd1:0"',
    'Last-Modified': 'Wed, 05 Aug 2026 13:47:25 GMT',
}


class SnapshotTests(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()

    def _store(self, payload=None, headers=None):
        with for_island(self.island):
            return store_snapshot(
                self.island,
                payload=payload or PAYLOAD,
                headers=headers or HEADERS_UPSTREAM,
                source_url='https://azoresbus.pt/static/json/tariffs.json',
            )

    def test_the_same_payload_twice_stores_one_row(self):
        self._store()
        self._store()
        self.assertEqual(TariffSnapshot.objects.count(), 1)

    def test_a_changed_payload_appends_and_retires_the_old_one(self):
        first = self._store()
        changed = {**PAYLOAD, 'date': '2027-01-01'}
        second = self._store(payload=changed)

        self.assertEqual(TariffSnapshot.objects.count(), 2)
        first.refresh_from_db()
        self.assertFalse(first.is_current)
        self.assertTrue(second.is_current)

    def test_upstream_freshness_signals_are_kept_not_invented(self):
        snapshot = self._store()
        self.assertEqual(snapshot.upstream_etag, '"80d474f2e024dd1:0"')
        self.assertIsNotNone(snapshot.upstream_modified_at)
        self.assertEqual(snapshot.effective_date.isoformat(), '2026-09-01')


class SerializerTests(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        with for_island(self.island):
            self.snapshot = store_snapshot(
                self.island, payload=PAYLOAD, headers=HEADERS_UPSTREAM,
                source_url='https://azoresbus.pt/static/json/tariffs.json',
            )

    def test_fare_units_round_trip_as_strings(self):
        """Never parsed into numeric ranges: "0 a 5" is a label, not a range."""
        payload = serialize_tariffs(self.snapshot)
        prices = payload['categories'][0]['tariffs'][0]['prices']
        for price in prices:
            self.assertIsInstance(price['band'], str)
        self.assertEqual(prices[0]['band'], '0 a 5')

    def test_the_redundant_group_level_is_flattened(self):
        payload = serialize_tariffs(self.snapshot)
        self.assertEqual(len(payload['categories']), 1)
        self.assertEqual(len(payload['categories'][0]['tariffs']), 2)

    def test_multiple_groups_are_merged_not_indexed(self):
        """Every category has one group today; tolerate more (02 §6)."""
        two_groups = {
            **PAYLOAD,
            'categories': [{
                'name': 'Passes',
                'groups': [
                    {'tariffs': [{'name': 'A', 'prices': [{'price': 1.0}]}]},
                    {'tariffs': [{'name': 'B', 'prices': [{'price': 2.0}]}]},
                ],
            }],
        }
        with for_island(self.island):
            snapshot = store_snapshot(
                self.island, payload=two_groups, headers={},
                source_url='https://x',
            )
        payload = serialize_tariffs(snapshot)
        self.assertEqual(
            [t['name'] for t in payload['categories'][0]['tariffs']], ['A', 'B'],
        )

    def test_a_flat_tariff_has_no_band(self):
        payload = serialize_tariffs(self.snapshot)
        flat = payload['categories'][0]['tariffs'][1]
        self.assertEqual(flat['prices'][0]['price'], 0.0)
        self.assertIsNone(flat['prices'][0].get('band'))

    def test_is_future_is_derived_from_the_effective_date(self):
        payload = serialize_tariffs(self.snapshot)
        self.assertIn('isFuture', payload)

    def test_notes_and_infos_are_carried_through(self):
        payload = serialize_tariffs(self.snapshot)
        self.assertIn('custo de 6', payload['notes'])
        self.assertEqual(payload['infos'][0]['url'], 'https://azoresbus.pt/x.pdf')

    def test_no_per_ride_fare_is_ever_computed(self):
        """98 §4 gap: nothing upstream gives km between two stops."""
        payload = serialize_tariffs(self.snapshot)
        self.assertNotIn('fare', payload)
        self.assertNotIn('price', payload)


class EndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.island = get_or_create_default_island()

    def test_404_when_no_snapshot_exists_yet(self):
        response = self.client.get('/api/v3/transit/tariffs', **HEADERS)
        self.assertEqual(response.status_code, 404)

    def test_returns_the_current_snapshot(self):
        with for_island(self.island):
            store_snapshot(
                self.island, payload=PAYLOAD, headers=HEADERS_UPSTREAM,
                source_url='https://azoresbus.pt/static/json/tariffs.json',
            )
        response = self.client.get('/api/v3/transit/tariffs', **HEADERS)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['effectiveDate'], '2026-09-01')
        self.assertEqual(
            body['categories'][0]['tariffs'][0]['prices'][0]['band'], '0 a 5',
        )


class FetchTests(TestCase):
    @patch('azoresbus.services_tariffs.requests.get')
    def test_a_304_stores_nothing_and_costs_nothing(self, mock_get):
        """Conditional GET: the daily run is free when fares have not moved."""
        from azoresbus.services_tariffs import sync_tariffs

        island = get_or_create_default_island()
        with for_island(island):
            store_snapshot(
                island, payload=PAYLOAD, headers=HEADERS_UPSTREAM,
                source_url='https://azoresbus.pt/static/json/tariffs.json',
            )
        mock_get.return_value = MagicMock(status_code=304, headers={}, ok=False)

        with for_island(island):
            result = sync_tariffs(island)

        self.assertFalse(result['changed'])
        self.assertEqual(TariffSnapshot.objects.count(), 1)
        sent = mock_get.call_args.kwargs['headers']
        self.assertEqual(sent.get('If-None-Match'), '"80d474f2e024dd1:0"')
