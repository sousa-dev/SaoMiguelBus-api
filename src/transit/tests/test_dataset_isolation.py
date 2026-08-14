"""98 B4: every reader must be pinned to one dataset.

Legacy `app_route.route` already contains 101, 102, 103, 105, 108-112, 200-219,
301-328 -- every one of which is also an AzoresBus `nameShort`. The moment both
networks exist in the same tables:

  - `get_line_v3` raises MultipleObjectsReturned on line 101;
  - pickers, the offline bundle and the v2 compat load emit both networks
    interleaved, which old clients cannot filter (98 B3);
  - directions, gmaps, route-weather and ads resolve stops with `.first()` and
    silently pick an arbitrary network's coordinates;
  - the directions cache serves one network's Google result for the other.

S1 lands the isolation with no cutover configured, so every reader resolves to
`legacy` and nothing user-visible changes. The S0 diff guard proves that.
"""

from __future__ import annotations

from datetime import time

from django.test import TestCase
from rest_framework.test import APIClient

from tenancy.services import for_island, get_or_create_default_island
from transit.services.service_backfill import backfill_legacy_services
from transit.models import (
    DATASET_AZORESBUS,
    DATASET_LEGACY,
    Calendar,
    Line,
    Operator,
    ServicePattern,
    Stop,
    StopTime,
    Trip,
)


HEADERS = {'HTTP_X_ISLAND': 'sao-miguel'}

# The colliding line code, and a stop name that exists in both networks.
COLLIDING_CODE = '101'
COLLIDING_STOP = 'PONTA DELGADA (ALFANDEGA)'
AZB_ONLY_STOP = 'LOMBA DO ALCAIDE'


def build_two_networks():
    """Legacy and AzoresBus rows that collide on line code and stop name."""
    island = get_or_create_default_island()
    operator_legacy, _ = Operator.objects.get_or_create(
        island=island, name='CRP', defaults={'contact': {}},
    )
    operator_azb, _ = Operator.objects.get_or_create(
        island=island, name='AzoresBus', defaults={'contact': {}},
    )
    calendar, _ = Calendar.objects.get_or_create(
        island=island, service_type=Calendar.WEEKDAY,
    )

    created = {}
    for dataset, operator, lat_base in (
        (DATASET_LEGACY, operator_legacy, 37.70),
        (DATASET_AZORESBUS, operator_azb, 37.80),
    ):
        line = Line.objects.create(
            island=island, dataset=dataset, code=COLLIDING_CODE,
            operator=operator, display_name=f'{dataset} 101',
        )
        origin = Stop.objects.create(
            island=island, dataset=dataset,
            name=COLLIDING_STOP, cleaned_name='ponta delgada (alfandega)',
            latitude=lat_base, longitude=-25.67,
        )
        destination = Stop.objects.create(
            island=island, dataset=dataset,
            name='RIBEIRA GRANDE', cleaned_name='ribeira grande',
            latitude=lat_base + 0.05, longitude=-25.51,
        )
        if dataset == DATASET_AZORESBUS:
            # Exists in the new network only. Any name-based resolver that
            # returns this while legacy is active has crossed the boundary.
            Stop.objects.create(
                island=island, dataset=dataset,
                name=AZB_ONLY_STOP, cleaned_name='lomba do alcaide',
                latitude=lat_base + 0.10, longitude=-25.40,
            )
        trip = Trip.objects.create(
            island=island, dataset=dataset, line=line, calendar=calendar,
            source=Trip.SOURCE_OPERATOR,
        )
        StopTime.objects.create(
            island=island, trip=trip, stop=origin,
            sequence=1, departure_time=time(8, 0),
        )
        StopTime.objects.create(
            island=island, trip=trip, stop=destination,
            sequence=2, departure_time=time(8, 30),
        )
        created[dataset] = {'line': line, 'trip': trip, 'origin': origin}

    # Production trips carry a ServicePattern (transit/migrations/0007 for
    # legacy, the sync for azoresbus). Without one, date-resolved search cannot
    # see them at all.
    backfill_legacy_services(island)
    pattern = ServicePattern.objects.create(
        island=island, dataset=DATASET_AZORESBUS, key='azb-everyday',
        monday=True, tuesday=True, wednesday=True, thursday=True,
        friday=True, saturday=True, sunday=True,
    )
    Trip.objects.filter(
        island=island, dataset=DATASET_AZORESBUS,
    ).update(service=pattern)
    for entry in created.values():
        entry['trip'].refresh_from_db()

    return island, created


class DatasetIsolationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.island, self.networks = build_two_networks()
        self.legacy_trip = self.networks[DATASET_LEGACY]['trip']
        self.azb_trip = self.networks[DATASET_AZORESBUS]['trip']

    # --- the one that raises today -----------------------------------------

    def test_get_line_v3_does_not_raise_multiple_objects_returned(self):
        from transit.services.v3 import get_line_v3

        with for_island(self.island):
            payload = get_line_v3(COLLIDING_CODE)

        self.assertIsNotNone(payload)
        trip_ids = {trip['id'] for trip in payload['trips']}
        self.assertIn(self.legacy_trip.id, trip_ids)
        self.assertNotIn(
            self.azb_trip.id, trip_ids,
            'line detail mixed both networks',
        )

    # --- v3 surface ---------------------------------------------------------

    def test_v3_stops_returns_one_network(self):
        response = self.client.get('/api/v3/transit/stops', **HEADERS)
        self.assertEqual(response.status_code, 200)
        stops = response.json()['stops']
        # NB: serialize_stops_v3 emits a short-name alias row for every stop
        # (98 section 4 gap), so names repeat even within one dataset. Identity
        # is what proves isolation.
        self.assertNotIn(AZB_ONLY_STOP, [s['name'] for s in stops])
        legacy_ids = set(
            Stop.objects.filter(dataset=DATASET_LEGACY).values_list('id', flat=True)
        )
        self.assertTrue(
            {s['id'] for s in stops} <= legacy_ids,
            'stops picker offered rows from the inactive network',
        )

    def test_v3_search_returns_one_network(self):
        response = self.client.get(
            '/api/v3/transit/search',
            {'origin': COLLIDING_STOP, 'destination': 'RIBEIRA GRANDE',
             'day': 'weekday', 'start': '00h00'},
            **HEADERS,
        )
        self.assertEqual(response.status_code, 200)
        ids = {row['id'] for row in response.json()['results']}
        self.assertEqual(ids, {self.legacy_trip.id})

    def test_v3_offline_bundle_returns_one_network(self):
        from transit.services.offline_bundle import build_offline_bundle

        with for_island(self.island):
            bundle = build_offline_bundle(self.island)

        route_ids = {route['id'] for route in bundle['routes']}
        self.assertEqual(route_ids, {self.legacy_trip.id})
        self.assertNotIn(AZB_ONLY_STOP, [s['name'] for s in bundle['stops']])
        self.assertEqual(bundle['counts']['stops'], 2)

    # --- v2 compat surface (the Expo offline fallback target, 98 B3) --------

    def test_v2_webapp_load_returns_one_network(self):
        from transit.services.compat import serialize_webapp_load_v2

        with for_island(self.island):
            payload = serialize_webapp_load_v2(self.island)

        header, *routes = payload
        route_ids = {route['id'] for route in routes}
        self.assertEqual(route_ids, {self.legacy_trip.id})
        self.assertNotIn(
            AZB_ONLY_STOP, header['stops'],
            'the Expo offline fallback would download both networks (98 B3)',
        )

    def test_v2_route_search_returns_one_network(self):
        response = self.client.get(
            '/api/v2/route',
            {'origin': COLLIDING_STOP, 'destination': 'RIBEIRA GRANDE',
             'day': 'weekday', 'start': '00h00'},
            **HEADERS,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row['id'] for row in response.json()},
                         {self.legacy_trip.id})

    # --- stop resolution by name (arbitrary .first() today) -----------------

    def test_route_weather_resolves_the_active_network_stop(self):
        from transit.services.route_weather import _resolve_stop

        with for_island(self.island):
            stop = _resolve_stop(self.island, COLLIDING_STOP)

        self.assertIsNotNone(stop)
        self.assertEqual(stop.dataset, DATASET_LEGACY)

    def test_ads_stop_matching_uses_one_network(self):
        """get_most_similar_stop scans every Stop row and returns a name."""
        from transit.services.ads import get_most_similar_stop

        with for_island(self.island):
            match = get_most_similar_stop('LOMBA DO ALCAIDE')

        self.assertNotEqual(
            match, AZB_ONLY_STOP,
            'ad targeting matched a stop from the inactive network',
        )

    # --- the directions cache key (98 section 4 gap) ------------------------

    def test_directions_cache_key_differs_per_dataset(self):
        from transit.services.directions_cache import build_cache_key

        common = {
            'island_key': 'sao-miguel',
            'origin': COLLIDING_STOP,
            'destination': 'RIBEIRA GRANDE',
            'day': '2026-09-01',
            'start': '08:00',
            'locale': 'pt',
        }
        self.assertNotEqual(
            build_cache_key(**common, dataset=DATASET_LEGACY),
            build_cache_key(**common, dataset=DATASET_AZORESBUS),
            'preview and live would share a cached Google result for 24h',
        )


class DatasetUniquenessTests(TestCase):
    """The uniqueness key must admit the same code in both networks."""

    def test_same_line_code_allowed_across_datasets(self):
        island, _ = build_two_networks()
        self.assertEqual(
            Line.objects.filter(island=island, code=COLLIDING_CODE).count(), 2,
        )

    def test_duplicate_code_within_one_dataset_still_rejected(self):
        from django.db import IntegrityError

        island = get_or_create_default_island()
        operator, _ = Operator.objects.get_or_create(
            island=island, name='CRP', defaults={'contact': {}},
        )
        Line.objects.create(
            island=island, dataset=DATASET_LEGACY, code='999', operator=operator,
        )
        with self.assertRaises(IntegrityError):
            Line.objects.create(
                island=island, dataset=DATASET_LEGACY, code='999',
                operator=operator,
            )
