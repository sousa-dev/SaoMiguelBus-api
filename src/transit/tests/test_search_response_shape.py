"""02 §7.1b: the sequence indices must reach the client.

`boarding.sequence` / `alighting.sequence` are load-bearing, not decorative.
The app pipes online results through `extractTripSegment`, which re-matches by
NAME and returns null when the destination name appears before the origin — so
the server can correctly pick 301's later C -> A and the client still throws the
trip away (98 B7). It can only stop doing that if it receives the indices.

Additive and optional: legacy results have no ExternalStop and omit the keys
rather than emitting nulls, so older clients are unaffected.
"""

from __future__ import annotations

from datetime import time

from django.test import TestCase
from rest_framework.test import APIClient

from azoresbus.models import ExternalStop
from tenancy.services import for_island, get_or_create_default_island
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
from transit.services.service_backfill import backfill_legacy_services

HEADERS = {'HTTP_X_ISLAND': 'sao-miguel'}


class SearchResponseShapeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.island = get_or_create_default_island()
        self.operator, _ = Operator.objects.get_or_create(
            island=self.island, name='AzoresBus', defaults={'contact': {}},
        )
        self.pattern = ServicePattern.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, key='everyday',
            monday=True, tuesday=True, wednesday=True, thursday=True,
            friday=True, saturday=True, sunday=True,
        )

    def _stop(self, name, dataset=DATASET_AZORESBUS):
        return Stop.objects.create(
            island=self.island, dataset=dataset, name=name,
            cleaned_name=name.lower(), latitude=37.7, longitude=-25.6,
        )

    def _azoresbus_trip(self):
        line = Line.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, code='101',
            operator=self.operator,
        )
        trip = Trip.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, line=line,
            service=self.pattern, source=Trip.SOURCE_OPERATOR, likes=5,
        )
        origin, destination = self._stop('ALFA'), self._stop('BRAVO')
        for index, (stop, hhmm, code) in enumerate(
            [(origin, time(8, 0), '1002'), (destination, time(8, 30), '5186')],
            start=1,
        ):
            external = ExternalStop.objects.create(
                island=self.island, dataset=DATASET_AZORESBUS,
                external_id=f'ext-{code}', code=code, name=stop.name,
                latitude=37.73, longitude=-25.67, stop=stop,
            )
            StopTime.objects.create(
                island=self.island, trip=trip, stop=stop,
                external_stop=external, sequence=index,
                departure_time=hhmm, day_offset=0,
            )
        return trip

    def _search(self, origin='ALFA', destination='BRAVO', dataset=None):
        params = {'origin': origin, 'destination': destination,
                  'day': 'weekday', 'start': '00h00'}
        if dataset:
            params['dataset'] = dataset
        response = self.client.get('/api/v3/transit/search', params, **HEADERS)
        self.assertEqual(response.status_code, 200)
        return response.json()['results']

    def test_boarding_and_alighting_reach_the_v3_response(self):
        self._azoresbus_trip()
        result = self._search(dataset=DATASET_AZORESBUS)[0]

        self.assertIn('boarding', result)
        self.assertIn('alighting', result)

    def test_the_sequence_indices_are_present_and_correct(self):
        """Without these the client re-matches names and drops the pair."""
        self._azoresbus_trip()
        result = self._search(dataset=DATASET_AZORESBUS)[0]

        self.assertEqual(result['boarding']['sequence'], 1)
        self.assertEqual(result['alighting']['sequence'], 2)

    def test_the_pole_code_reaches_the_client(self):
        """The number printed on the pole is the best disambiguation there is."""
        self._azoresbus_trip()
        result = self._search(dataset=DATASET_AZORESBUS)[0]

        self.assertEqual(result['boarding']['code'], '1002')
        self.assertEqual(result['alighting']['code'], '5186')
        self.assertIn('lat', result['boarding'])
        self.assertIn('lon', result['boarding'])

    def test_day_offset_travels_so_a_client_can_badge_plus_one(self):
        self._azoresbus_trip()
        result = self._search(dataset=DATASET_AZORESBUS)[0]
        self.assertEqual(result['boarding']['dayOffset'], 0)

    def test_legacy_results_omit_the_keys_rather_than_sending_nulls(self):
        """Additive and optional: older clients must be unaffected."""
        operator, _ = Operator.objects.get_or_create(
            island=self.island, name='CRP', defaults={'contact': {}},
        )
        calendar, _ = Calendar.objects.get_or_create(
            island=self.island, service_type=Calendar.WEEKDAY,
        )
        line = Line.objects.create(
            island=self.island, dataset=DATASET_LEGACY, code='208',
            operator=operator,
        )
        trip = Trip.objects.create(
            island=self.island, dataset=DATASET_LEGACY, line=line,
            calendar=calendar, source=Trip.SOURCE_OPERATOR,
        )
        origin = self._stop('CHARLIE', DATASET_LEGACY)
        destination = self._stop('DELTA', DATASET_LEGACY)
        StopTime.objects.create(
            island=self.island, trip=trip, stop=origin, sequence=1,
            departure_time=time(9, 0),
        )
        StopTime.objects.create(
            island=self.island, trip=trip, stop=destination, sequence=2,
            departure_time=time(9, 30),
        )
        with for_island(self.island):
            backfill_legacy_services(self.island)

        result = self._search('CHARLIE', 'DELTA', dataset=DATASET_LEGACY)[0]
        self.assertNotIn('boarding', result)
        self.assertNotIn('alighting', result)

    def test_the_existing_keys_are_unchanged(self):
        """Additive means additive: nothing older clients read may move."""
        self._azoresbus_trip()
        result = self._search(dataset=DATASET_AZORESBUS)[0]

        for key in ('id', 'route', 'origin', 'destination', 'start', 'end',
                    'typeOfDay', 'likesPercent', 'dislikesPercent',
                    'information', 'stops'):
            self.assertIn(key, result)
