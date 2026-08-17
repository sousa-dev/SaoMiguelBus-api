"""One-transfer journey search.

The case that motivated it: Capelas -> Furnas. No single line runs it, so
`/transit/search` returns nothing and the app said no route exists. These tests
build the same shape in miniature -- a western line into a hub, an eastern line
out of it -- and pin the rules that decide whether a connection is real.
"""

from __future__ import annotations

from datetime import date, time

from django.test import TestCase
from rest_framework.test import APIClient

from azoresbus.models import ExternalStop
from tenancy.services import for_island, get_or_create_default_island
from transit.models import (
    DATASET_AZORESBUS,
    Holiday,
    Line,
    Operator,
    ServicePattern,
    Stop,
    StopTime,
    Trip,
)
from transit.services.journeys import search_journeys
from transit.services.transfer_points import MIN_TRANSFER_MINUTES

HEADERS = {'HTTP_X_ISLAND': 'sao-miguel'}

# Far enough apart that the grid never accidentally joins two villages.
CAPELAS = (37.828, -25.677)
HUB = (37.740, -25.668)
FURNAS = (37.772, -25.310)


class JourneyTestCase(TestCase):
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

    def stop(self, name, position, dataset=DATASET_AZORESBUS):
        latitude, longitude = position
        return Stop.objects.create(
            island=self.island, dataset=dataset, name=name,
            cleaned_name=name.lower(), latitude=latitude, longitude=longitude,
        )

    def line(self, code, dataset=DATASET_AZORESBUS):
        return Line.objects.create(
            island=self.island, dataset=dataset, code=code, operator=self.operator,
        )

    def trip(self, line, schedule, *, service=None, dataset=DATASET_AZORESBUS,
             poles=False, likes=10):
        """`schedule` is [(stop, 'HH:MM'), ...] or [(stop, 'HH:MM', day_offset), ...]."""
        trip = Trip.objects.create(
            island=self.island, dataset=dataset, line=line,
            service=service or self.everyday, source=Trip.SOURCE_OPERATOR,
            likes=likes,
        )
        for index, row in enumerate(schedule, start=1):
            stop, hhmm = row[0], row[1]
            day_offset = row[2] if len(row) > 2 else 0
            hour, minute = map(int, hhmm.split(':'))
            external = None
            if poles:
                external = ExternalStop.objects.create(
                    island=self.island, dataset=dataset,
                    external_id=f'ext-{trip.id}-{index}', code=f'P{index:02d}',
                    name=stop.name, latitude=stop.latitude,
                    longitude=stop.longitude, stop=stop,
                )
            StopTime.objects.create(
                island=self.island, trip=trip, stop=stop, external_stop=external,
                sequence=index, departure_time=time(hour, minute),
                day_offset=day_offset,
            )
        return trip

    def search(self, origin='Capelas', destination='Furnas', day='weekday',
               start='00h00', dataset=DATASET_AZORESBUS):
        with for_island(self.island):
            return search_journeys(
                origin=origin, destination=destination, day=day,
                start_time=start, dataset=dataset,
            )


class TransferJourneyTests(JourneyTestCase):
    def setUp(self):
        super().setUp()
        self.capelas = self.stop('CAPELAS (IGREJA)', CAPELAS)
        self.hub = self.stop('PONTA DELGADA', HUB)
        self.furnas = self.stop('FURNAS', FURNAS)

        self.west = self.line('315')
        self.east = self.line('110')

        self.trip(self.west, [(self.capelas, '08:10'), (self.hub, '08:55')])
        self.trip(self.east, [(self.hub, '09:30'), (self.furnas, '11:05')])

    def test_a_two_bus_journey_is_found_where_search_finds_nothing(self):
        journeys = self.search()

        self.assertEqual(len(journeys), 1)
        journey = journeys[0]
        self.assertEqual(journey.transfers, 1)
        self.assertEqual(
            [leg.trip.line.code for leg in journey.legs], ['315', '110'],
        )

    def test_the_times_are_the_riders_times_not_the_trips(self):
        journey = self.search()[0]

        self.assertEqual(journey.legs[0].board.departure_time, time(8, 10))
        self.assertEqual(journey.legs[-1].alight.departure_time, time(11, 5))
        self.assertEqual(journey.waits, (35,))

    def test_a_connection_that_cannot_be_made_is_not_offered(self):
        """Leg B leaving before leg A lands is not a journey, it is a miss."""
        Trip.objects.filter(line=self.east).delete()
        self.trip(self.east, [(self.hub, '08:56'), (self.furnas, '10:30')])

        self.assertEqual(self.search(), [])

    def test_the_minimum_transfer_buffer_is_enforced(self):
        """Landing at 08:55 does not let you catch an 08:58 on a rural network."""
        Trip.objects.filter(line=self.east).delete()
        self.trip(
            self.east,
            [(self.hub, '08:5%d' % (5 + MIN_TRANSFER_MINUTES - 1)), (self.furnas, '10:30')],
        )

        self.assertEqual(self.search(), [])

    def test_a_change_onto_the_same_line_is_not_a_transfer(self):
        """Two trips on one line is the same bus continuing, not a change."""
        Trip.objects.filter(line=self.east).delete()
        self.trip(self.west, [(self.hub, '09:30'), (self.furnas, '11:05')])

        self.assertEqual(self.search(), [])

    def test_a_walkable_stop_at_the_interchange_still_connects(self):
        """Arrival and departure bays with different names, ~120 m apart."""
        Trip.objects.filter(line=self.east).delete()
        annex = self.stop('PONTA DELGADA (TERMINAL)', (HUB[0] + 0.0011, HUB[1]))
        self.trip(self.east, [(annex, '09:30'), (self.furnas, '11:05')])

        journeys = self.search()
        self.assertEqual(len(journeys), 1)
        self.assertEqual(journeys[0].legs[1].board.stop_id, annex.id)

    def test_a_stop_across_town_does_not_count_as_an_interchange(self):
        Trip.objects.filter(line=self.east).delete()
        far = self.stop('OUTRO SITIO', (HUB[0] + 0.02, HUB[1]))
        self.trip(self.east, [(far, '09:30'), (self.furnas, '11:05')])

        self.assertEqual(self.search(), [])

    def test_a_direct_bus_beats_and_removes_a_slower_two_bus_journey(self):
        self.trip(self.line('999'), [(self.capelas, '08:10'), (self.furnas, '10:00')])

        journeys = self.search()
        self.assertEqual([journey.transfers for journey in journeys], [0])

    def test_a_direct_bus_does_not_remove_a_journey_that_leaves_later(self):
        """Dominance is all three axes at once, not just arrival."""
        self.trip(self.line('999'), [(self.capelas, '06:00'), (self.furnas, '12:00')])

        journeys = self.search()
        self.assertEqual(sorted(journey.transfers for journey in journeys), [0, 1])

    def test_the_start_time_filter_applies_to_the_first_boarding(self):
        self.assertEqual(self.search(start='09h00'), [])
        self.assertEqual(len(self.search(start='08h00')), 1)

    def test_service_patterns_are_honoured(self):
        """A line that does not run today cannot be half of today's journey."""
        term_only = ServicePattern.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, key='tue-thu',
            tuesday=True, thursday=True,
        )
        Trip.objects.filter(line=self.east).delete()
        self.trip(
            self.east, [(self.hub, '09:30'), (self.furnas, '11:05')],
            service=term_only,
        )

        self.assertEqual(self.search(day='weekday'), [])
        self.assertEqual(len(self.search(day='2026-08-18')), 1)   # a Tuesday
        self.assertEqual(self.search(day='2026-08-19'), [])       # a Wednesday

    def test_a_holiday_resolves_to_the_sunday_service(self):
        Holiday.objects.create(
            island=self.island, date=date(2026, 8, 19), name='Test holiday',
        )
        sunday_only = ServicePattern.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, key='sun', sunday=True,
        )
        Trip.objects.filter(line=self.east).delete()
        self.trip(
            self.east, [(self.hub, '09:30'), (self.furnas, '11:05')],
            service=sunday_only,
        )

        # 19 August 2026 is a Wednesday, but the holiday makes it a Sunday.
        self.assertEqual(len(self.search(day='2026-08-19')), 1)

    def test_a_journey_crossing_midnight_keeps_its_order(self):
        Trip.objects.filter(line=self.east).delete()
        self.trip(
            self.east,
            [(self.hub, '23:50'), (self.furnas, '00:40', 1)],
        )
        Trip.objects.filter(line=self.west).delete()
        self.trip(self.west, [(self.capelas, '22:30'), (self.hub, '23:15')])

        journey = self.search()[0]
        self.assertGreater(journey.arrival, journey.departure)
        self.assertEqual(journey.legs[-1].alight.day_offset, 1)


class ProductionFindingsTests(JourneyTestCase):
    """Three faults the deployed endpoint showed on real São Miguel data."""

    def setUp(self):
        super().setUp()
        self.capelas = self.stop('CAPELAS (IGREJA)', CAPELAS)
        self.capelas_rossio = self.stop(
            'CAPELAS (ROSSIO)', (CAPELAS[0] + 0.01, CAPELAS[1]),
        )
        self.hub = self.stop('PONTA DELGADA', HUB)
        self.furnas = self.stop('FURNAS', FURNAS)

    def test_a_leg_whose_clock_runs_backwards_is_never_offered(self):
        """Legacy line 206 reaches sequence 12 at 08h20 and 13 at 08h10.

        The sequence is in order; only the clock disagrees, so the pair matcher
        cannot catch it. `/transit/search` has shipped these rows for years.
        """
        # Mirrors the shape of the real row: the ORIGIN is timed later than the
        # DESTINATION that follows it in sequence.
        self.trip(
            self.line('206'),
            [(self.hub, '08:00'), (self.capelas, '08:20'), (self.furnas, '08:10')],
        )

        self.assertEqual(self.search(), [])

    def test_a_backwards_leg_does_not_poison_a_transfer(self):
        self.trip(self.line('206'), [(self.capelas, '08:20'), (self.hub, '08:10')])
        self.trip(self.line('110'), [(self.hub, '09:30'), (self.furnas, '11:05')])

        # The only route to Furnas runs through a leg that arrives before it
        # departs -- offering it would let the connection satisfy the transfer
        # buffer against a time the bus never reaches.
        self.assertEqual(self.search(), [])

    def test_an_absurd_wait_is_not_a_journey(self):
        """Production: ride 2 minutes at 00h53, wait 5h29, then take the 06h24.

        Nothing dominates it -- it departs before everything else -- so only a
        wait rule removes it.
        """
        self.trip(self.line('215'), [(self.capelas, '00:53'), (self.capelas_rossio, '00:55')])
        self.trip(self.line('218'), [(self.capelas_rossio, '06:24'), (self.hub, '06:58')])

        journeys = self.search(destination='Ponta Delgada')

        # The 06h24 direct still stands -- Rossio is in the Capelas area, so
        # that bus was always a direct ride. What must not survive is the
        # 00h53 hop bolted onto the front of it.
        self.assertEqual([journey.transfers for journey in journeys], [0])
        self.assertEqual(journeys[0].legs[0].board.departure_time, time(6, 24))

    def test_a_long_wait_survives_when_the_ride_is_long_too(self):
        """Saturday's only Capelas -> Furnas connection waits 241 minutes.

        Removing it would put the pair back to "no connection" -- the falsehood
        this feature exists to remove.
        """
        self.trip(self.line('207'), [(self.capelas, '09:59'), (self.hub, '10:59')])
        self.trip(self.line('318'), [(self.hub, '15:00'), (self.furnas, '16:30')])

        journeys = self.search()
        self.assertEqual(len(journeys), 1)
        self.assertEqual(sum(journeys[0].waits), 241)

    def test_searching_a_place_to_itself_returns_nothing(self):
        """Production answered Capelas -> Capelas with 12 itineraries."""
        self.trip(
            self.line('215'),
            [(self.capelas, '08:00'), (self.capelas_rossio, '08:05'),
             (self.hub, '08:40')],
        )

        self.assertEqual(self.search(origin='Capelas', destination='Capelas'), [])

    def test_two_named_stops_in_one_village_is_still_a_real_ride(self):
        """The same-place guard compares SETS, so this must keep working."""
        self.trip(
            self.line('215'),
            [(self.capelas, '08:00'), (self.capelas_rossio, '08:05')],
        )

        journeys = self.search(
            origin='CAPELAS (IGREJA)', destination='CAPELAS (ROSSIO)',
        )
        self.assertEqual(len(journeys), 1)
        self.assertEqual(journeys[0].transfers, 0)


class DegenerateCoordinateTests(JourneyTestCase):
    """Null Island must never become an interchange.

    Two stops with missing coordinates both sit at (0, 0), measure zero metres
    apart, and would otherwise connect two villages 40 km apart -- the worst
    failure available here, because a rider acts on it and is stranded.
    """

    def setUp(self):
        super().setUp()
        self.capelas = self.stop('CAPELAS (IGREJA)', CAPELAS)
        self.furnas = self.stop('FURNAS', FURNAS)
        self.nowhere_a = self.stop('SEM COORDENADAS A', (0.0, 0.0))
        self.nowhere_b = self.stop('SEM COORDENADAS B', (0.0, 0.0))

        self.trip(self.line('315'), [(self.capelas, '08:10'), (self.nowhere_a, '08:55')])
        self.trip(self.line('110'), [(self.nowhere_b, '09:30'), (self.furnas, '11:05')])

    def test_two_unlocated_stops_do_not_become_one_interchange(self):
        self.assertEqual(self.search(), [])

    def test_an_unlocated_stop_still_works_as_a_same_stop_change(self):
        """Changing bus where you already stand needs no coordinates at all."""
        east = Line.objects.get(dataset=DATASET_AZORESBUS, code='110')
        Trip.objects.filter(line=east).delete()
        self.trip(east, [(self.nowhere_a, '09:30'), (self.furnas, '11:05')])

        journeys = self.search()
        self.assertEqual(len(journeys), 1)
        self.assertEqual(journeys[0].transfers, 1)


class DirectJourneyTests(JourneyTestCase):
    def test_a_direct_ride_is_returned_as_a_single_leg_journey(self):
        alfa = self.stop('ALFA', CAPELAS)
        bravo = self.stop('BRAVO', HUB)
        self.trip(self.line('101'), [(alfa, '08:00'), (bravo, '08:30')])

        journeys = self.search(origin='ALFA', destination='BRAVO')
        self.assertEqual(len(journeys), 1)
        self.assertEqual(journeys[0].transfers, 0)
        self.assertEqual(journeys[0].waits, ())

    def test_a_loop_yields_one_row_per_trip_not_one_per_pair(self):
        """`select_pair` owns this tie-break; journeys must not re-decide it."""
        alfa = self.stop('ALFA', CAPELAS)
        bravo = self.stop('BRAVO', HUB)
        self.trip(
            self.line('301'),
            [(alfa, '06:00'), (bravo, '06:30'), (alfa, '07:00'), (bravo, '07:30')],
        )

        journeys = self.search(origin='ALFA', destination='BRAVO')
        self.assertEqual(len(journeys), 1)

    def test_an_unresolvable_stop_returns_empty_not_an_error(self):
        self.assertEqual(self.search(origin='NOWHERE', destination='ALSO NOWHERE'), [])

    def test_a_blank_query_is_rejected(self):
        self.assertIsNone(self.search(origin='', destination='BRAVO'))


class JourneyResponseShapeTests(JourneyTestCase):
    """02 §7.1b applies to legs too -- the client slices on `sequence`."""

    def setUp(self):
        super().setUp()
        self.capelas = self.stop('CAPELAS (IGREJA)', CAPELAS)
        self.hub = self.stop('PONTA DELGADA', HUB)
        self.furnas = self.stop('FURNAS', FURNAS)
        self.trip(
            self.line('315'),
            [(self.capelas, '08:10'), (self.hub, '08:55')],
            poles=True,
        )
        self.trip(
            self.line('110'),
            [(self.hub, '09:30'), (self.furnas, '11:05')],
            poles=True,
        )

    def get(self, **overrides):
        params = {
            'origin': 'Capelas', 'destination': 'Furnas',
            'day': 'weekday', 'start': '00h00', 'dataset': DATASET_AZORESBUS,
        }
        params.update(overrides)
        response = self.client.get('/api/v3/transit/journeys', params, **HEADERS)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_the_payload_alternates_ride_and_transfer_legs(self):
        journey = self.get()['journeys'][0]

        self.assertEqual(
            [leg['kind'] for leg in journey['legs']], ['ride', 'transfer', 'ride'],
        )

    def test_the_transfer_leg_names_the_place_and_the_wait(self):
        transfer = self.get()['journeys'][0]['legs'][1]

        self.assertEqual(transfer['at'], 'PONTA DELGADA')
        self.assertEqual(transfer['waitMinutes'], 35)
        self.assertEqual(transfer['walkMinutes'], 0)
        self.assertEqual(transfer['fromRoute'], '315')
        self.assertEqual(transfer['toRoute'], '110')

    def test_journey_level_totals_are_present(self):
        journey = self.get()['journeys'][0]

        self.assertEqual(journey['transfers'], 1)
        self.assertEqual(journey['start'], '08h10')
        self.assertEqual(journey['end'], '11h05')
        self.assertEqual(journey['durationMinutes'], 175)
        self.assertEqual(journey['waitMinutes'], 35)

    def test_each_ride_leg_carries_its_own_trimmed_stop_list(self):
        legs = [leg for leg in self.get()['journeys'][0]['legs'] if leg['kind'] == 'ride']

        self.assertEqual([stop['name'] for stop in legs[0]['stops']],
                         ['CAPELAS (IGREJA)', 'PONTA DELGADA'])
        self.assertEqual([stop['name'] for stop in legs[1]['stops']],
                         ['PONTA DELGADA', 'FURNAS'])

    def test_the_sequence_indices_reach_the_client(self):
        ride = self.get()['journeys'][0]['legs'][0]

        self.assertEqual(ride['board']['sequence'], 1)
        self.assertEqual(ride['alight']['sequence'], 2)

    def test_pole_identity_reaches_the_client_when_upstream_gave_it(self):
        ride = self.get()['journeys'][0]['legs'][0]

        self.assertEqual(ride['boarding']['code'], 'P01')
        self.assertIn('lat', ride['boarding'])

    def test_the_journey_id_is_stable_and_names_both_trips(self):
        journey = self.get()['journeys'][0]
        trip_ids = [leg['tripId'] for leg in journey['legs'] if leg['kind'] == 'ride']

        self.assertEqual(journey['id'], ':'.join(str(i) for i in trip_ids))

    def test_a_missing_origin_is_a_400(self):
        response = self.client.get(
            '/api/v3/transit/journeys', {'destination': 'Furnas'}, **HEADERS,
        )
        self.assertEqual(response.status_code, 400)


class LegacyDatasetJourneyTests(JourneyTestCase):
    """Legacy rows have no ExternalStop; the keys are omitted, never null."""

    def test_pole_keys_are_absent_rather_than_null(self):
        from transit.models import DATASET_LEGACY

        legacy_everyday = ServicePattern.objects.create(
            island=self.island, dataset=DATASET_LEGACY, key='everyday',
            monday=True, tuesday=True, wednesday=True, thursday=True,
            friday=True, saturday=True, sunday=True,
        )
        alfa = self.stop('ALFA', CAPELAS, dataset=DATASET_LEGACY)
        bravo = self.stop('BRAVO', HUB, dataset=DATASET_LEGACY)
        line = self.line('101', dataset=DATASET_LEGACY)
        self.trip(
            line, [(alfa, '08:00'), (bravo, '08:30')],
            dataset=DATASET_LEGACY, service=legacy_everyday,
        )

        response = self.client.get(
            '/api/v3/transit/journeys',
            {'origin': 'ALFA', 'destination': 'BRAVO', 'day': 'weekday',
             'start': '00h00', 'dataset': DATASET_LEGACY},
            **HEADERS,
        )
        self.assertEqual(response.status_code, 200)
        ride = response.json()['journeys'][0]['legs'][0]

        self.assertNotIn('boarding', ride)
        self.assertNotIn('alighting', ride)
