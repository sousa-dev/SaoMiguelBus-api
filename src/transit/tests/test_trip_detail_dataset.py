"""Trip and line detail must be addressable for the previewed network.

Reported from the field as "Trip not found" on every result tapped while
previewing. The cause was not one bad trip: `transit_trip_detail_view` called
`get_trip_v3(trip_id)` without passing `?dataset=` through, so the dataset
resolved from the server's own date. Previewing happens BEFORE the cutover, that
resolves to `legacy`, and the ids come from a `?dataset=azoresbus` search -- so
they could never be looked up again.

Fixing that alone would have turned the 404 into a 500, because
`serialize_trip_detail` dereferenced `trip.calendar`, which the AzoresBus importer
writes as None. Both are covered here.
"""

from __future__ import annotations

from datetime import time

from django.test import TestCase
from rest_framework.test import APIClient

from tenancy.services import get_or_create_default_island
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


class TripDetailDatasetTests(TestCase):
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
        # An AzoresBus trip carries a ServicePattern and NO Calendar, exactly as
        # azoresbus/services_import.py writes it.
        line = Line.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, code='101',
            operator=self.operator,
        )
        self.trip = Trip.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, line=line,
            calendar=None, service=self.pattern, source=Trip.SOURCE_OPERATOR,
        )
        stop = Stop.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, name='ALFA',
            cleaned_name='alfa', latitude=37.7, longitude=-25.6,
        )
        StopTime.objects.create(
            island=self.island, trip=self.trip, stop=stop, sequence=1,
            departure_time=time(8, 0), day_offset=0,
        )

    def test_a_previewed_trip_is_reachable_with_the_dataset(self):
        response = self.client.get(
            f'/api/v3/transit/trips/{self.trip.id}?dataset=azoresbus', **HEADERS,
        )
        self.assertEqual(response.status_code, 200, response.content[:200])
        self.assertEqual(response.json()['id'], self.trip.id)

    def test_a_calendarless_trip_serializes_instead_of_500ing(self):
        """trip.calendar is None on every AzoresBus trip."""
        response = self.client.get(
            f'/api/v3/transit/trips/{self.trip.id}?dataset=azoresbus', **HEADERS,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['typeOfDay'])

    def test_without_the_param_it_still_resolves_by_date(self):
        """No cutover configured means legacy, so the AzoresBus trip is absent."""
        response = self.client.get(f'/api/v3/transit/trips/{self.trip.id}', **HEADERS)
        self.assertEqual(response.status_code, 404)

    def test_a_legacy_trip_is_unaffected(self):
        calendar, _ = Calendar.objects.get_or_create(
            island=self.island, service_type=Calendar.WEEKDAY,
        )
        operator, _ = Operator.objects.get_or_create(
            island=self.island, name='CRP', defaults={'contact': {}},
        )
        line = Line.objects.create(
            island=self.island, dataset=DATASET_LEGACY, code='208', operator=operator,
        )
        trip = Trip.objects.create(
            island=self.island, dataset=DATASET_LEGACY, line=line,
            calendar=calendar, source=Trip.SOURCE_OPERATOR,
        )
        stop = Stop.objects.create(
            island=self.island, dataset=DATASET_LEGACY, name='CHARLIE',
            cleaned_name='charlie', latitude=37.7, longitude=-25.6,
        )
        StopTime.objects.create(
            island=self.island, trip=trip, stop=stop, sequence=1,
            departure_time=time(9, 0),
        )

        response = self.client.get(f'/api/v3/transit/trips/{trip.id}', **HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['typeOfDay'], Calendar.WEEKDAY)

    def test_a_previewed_trip_can_be_voted_on(self):
        """The vote endpoint had the same gap, and a vote is a write."""
        response = self.client.post(
            f'/api/v3/transit/trips/{self.trip.id}/vote?dataset=azoresbus',
            {'vote': 'like'}, format='json', **HEADERS,
        )
        self.assertEqual(response.status_code, 200, response.content[:200])
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.likes, 1)

    def test_a_previewed_line_is_reachable(self):
        response = self.client.get(
            '/api/v3/transit/lines/101?dataset=azoresbus', **HEADERS,
        )
        self.assertEqual(response.status_code, 200, response.content[:200])
