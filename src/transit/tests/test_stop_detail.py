"""`GET /api/v3/transit/stops/{id}` — the stop page's data.

The rule that matters: departures resolve through the SAME `eligible_trips` the
search uses. A stop page that promises a bus `/journeys` would refuse to plan is
worse than one that shows nothing, because a rider walks to the stop for it.
"""

from __future__ import annotations

from datetime import date, time

from django.test import TestCase
from rest_framework.test import APIClient

from azoresbus.models import ExternalStop
from tenancy.services import get_or_create_default_island
from transit.models import (
    DATASET_AZORESBUS,
    DATASET_LEGACY,
    Holiday,
    Line,
    Operator,
    ServicePattern,
    Stop,
    StopTime,
    Trip,
)

HEADERS = {'HTTP_X_ISLAND': 'sao-miguel'}
HUB = (37.7412, -25.6756)


class StopDetailTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.island = get_or_create_default_island()
        self.operator, _ = Operator.objects.get_or_create(
            island=self.island, name='AzoresBus', defaults={'contact': {}},
        )
        self.everyday = ServicePattern.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, key='everyday',
            monday=True, tuesday=True, wednesday=True, thursday=True,
            friday=True, saturday=True, sunday=True,
        )
        self.hub = Stop.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, name='PONTA DELGADA',
            cleaned_name='ponta delgada', latitude=HUB[0], longitude=HUB[1],
        )
        self.far = Stop.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, name='FURNAS',
            cleaned_name='furnas', latitude=37.772, longitude=-25.310,
        )

    def pole(self, stop, code, offset=0.0):
        return ExternalStop.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS,
            external_id=f'ext-{code}', code=code, name=stop.name,
            latitude=stop.latitude + offset, longitude=stop.longitude,
            stop=stop,
        )

    def departure(self, code, hhmm, *, service=None, pole=None, headsign='',
                  dataset=DATASET_AZORESBUS):
        line, _ = Line.objects.get_or_create(
            island=self.island, dataset=dataset, code=code,
            defaults={'operator': self.operator},
        )
        trip = Trip.objects.create(
            island=self.island, dataset=dataset, line=line,
            service=service or self.everyday, source=Trip.SOURCE_OPERATOR,
            headsign=headsign,
        )
        hour, minute = map(int, hhmm.split(':'))
        StopTime.objects.create(
            island=self.island, trip=trip, stop=self.hub, external_stop=pole,
            sequence=1, departure_time=time(hour, minute),
        )
        StopTime.objects.create(
            island=self.island, trip=trip, stop=self.far,
            sequence=2, departure_time=time((hour + 1) % 24, minute),
        )
        return trip

    def get(self, stop=None, **params):
        params.setdefault('dataset', DATASET_AZORESBUS)
        response = self.client.get(
            f'/api/v3/transit/stops/{(stop or self.hub).id}', params, **HEADERS,
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_it_returns_the_stop_and_its_position(self):
        body = self.get()

        self.assertEqual(body['name'], 'PONTA DELGADA')
        self.assertAlmostEqual(body['lat'], HUB[0])
        self.assertAlmostEqual(body['lon'], HUB[1])

    def test_it_lists_every_pole_with_its_printed_code(self):
        """The centroid can sit mid-road; the pole is where you actually stand."""
        self.pole(self.hub, 'A12')
        self.pole(self.hub, 'A13', offset=0.0005)

        poles = self.get()['poles']
        self.assertEqual([p['code'] for p in poles], ['A12', 'A13'])
        self.assertNotAlmostEqual(poles[0]['lat'], poles[1]['lat'])

    def test_it_lists_the_lines_that_serve_it_once_each(self):
        self.departure('110', '09:00')
        self.departure('110', '10:00')
        self.departure('219', '09:30')

        self.assertEqual(self.get()['lines'], ['110', '219'])

    def test_departures_are_in_time_order(self):
        self.departure('110', '10:00')
        self.departure('219', '08:00')
        self.departure('318', '09:00')

        body = self.get()
        self.assertEqual([d['time'] for d in body['departures']],
                         ['08h00', '09h00', '10h00'])

    def test_departures_start_from_the_requested_time(self):
        self.departure('110', '08:00')
        self.departure('219', '14:00')

        body = self.get(start='12h00')
        self.assertEqual([d['time'] for d in body['departures']], ['14h00'])

    def test_a_departure_says_where_the_bus_is_going(self):
        self.departure('110', '09:00', headsign='FURNAS')

        self.assertEqual(self.get()['departures'][0]['headsign'], 'FURNAS')

    def test_the_pole_code_travels_with_the_departure(self):
        """Which side of the road this particular bus leaves from."""
        pole = self.pole(self.hub, 'A12')
        self.departure('110', '09:00', pole=pole)

        self.assertEqual(self.get()['departures'][0]['code'], 'A12')

    def test_service_rules_are_the_same_ones_search_uses(self):
        """A stop page must never promise a bus a journey search would refuse."""
        term_only = ServicePattern.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, key='tue-thu',
            tuesday=True, thursday=True,
        )
        self.departure('112', '09:00', service=term_only)

        self.assertEqual(self.get(day='weekday')['departures'], [])
        self.assertEqual(len(self.get(day='2026-08-18')['departures']), 1)  # Tuesday
        self.assertEqual(self.get(day='2026-08-19')['departures'], [])      # Wednesday

    def test_a_holiday_resolves_to_the_sunday_service(self):
        Holiday.objects.create(
            island=self.island, date=date(2026, 8, 19), name='Test holiday',
        )
        sunday = ServicePattern.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, key='sun', sunday=True,
        )
        self.departure('110', '09:00', service=sunday)

        # A Wednesday, but the holiday makes it a Sunday.
        self.assertEqual(len(self.get(day='2026-08-19')['departures']), 1)

    def test_the_departure_list_is_capped_but_the_line_list_is_not(self):
        """Lines answer "what stops here"; departures answer "is one soon"."""
        from transit.services.stops import DEFAULT_DEPARTURE_LIMIT

        for index in range(DEFAULT_DEPARTURE_LIMIT + 6):
            self.departure(f'L{index:02d}', f'{6 + index % 12:02d}:00')

        body = self.get()
        self.assertEqual(len(body['departures']), DEFAULT_DEPARTURE_LIMIT)
        self.assertEqual(len(body['lines']), DEFAULT_DEPARTURE_LIMIT + 6)

    def test_an_unknown_stop_is_a_404(self):
        response = self.client.get('/api/v3/transit/stops/999999', **HEADERS)
        self.assertEqual(response.status_code, 404)

    def test_a_stop_from_the_other_dataset_is_not_reachable(self):
        legacy = Stop.objects.create(
            island=self.island, dataset=DATASET_LEGACY, name='ALFA',
            cleaned_name='alfa', latitude=HUB[0], longitude=HUB[1],
        )
        response = self.client.get(
            f'/api/v3/transit/stops/{legacy.id}',
            {'dataset': DATASET_AZORESBUS}, **HEADERS,
        )
        self.assertEqual(response.status_code, 404)

    def test_legacy_has_no_poles_but_still_answers(self):
        legacy = Stop.objects.create(
            island=self.island, dataset=DATASET_LEGACY, name='ALFA',
            cleaned_name='alfa', latitude=HUB[0], longitude=HUB[1],
        )
        response = self.client.get(
            f'/api/v3/transit/stops/{legacy.id}',
            {'dataset': DATASET_LEGACY}, **HEADERS,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['poles'], [])
