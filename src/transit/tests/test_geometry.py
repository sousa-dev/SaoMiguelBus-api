"""Journey geometry: trimming a stored trip polyline to the leg a rider travels.

Where possible these run against the REAL captured upstream shape
(`azoresbus/tests/fixtures/journey_9_237.json`, 916 points over 36 km) rather
than a synthetic squiggle, because the properties that matter -- that a trimmed
path starts and ends at the right stops, and stays on the island -- are only
meaningful against geometry with real road curvature in it.
"""

from __future__ import annotations

import json
import pathlib
from datetime import time

from django.test import TestCase

from azoresbus.models import ExternalStop
from shared.geo import (
    decode_polyline,
    encode_polyline,
    haversine_km,
    is_plausible_route_coordinates,
)
from tenancy.services import get_or_create_default_island
from transit.models import (
    DATASET_AZORESBUS,
    DATASET_LEGACY,
    Line,
    Operator,
    ServicePattern,
    Stop,
    StopTime,
    Trip,
)
from transit.services.geometry import (
    MAX_STOP_TO_SHAPE_KM,
    leg_geometry,
    stop_time_position,
    trim_shape,
    trip_shape,
)

FIXTURE = (
    pathlib.Path(__file__).resolve().parents[2]
    / 'azoresbus' / 'tests' / 'fixtures' / 'journey_9_237.json'
)

# São Miguel, generously bounded.
BBOX = (37.6, 37.95, -25.9, -25.1)


def real_shape() -> str:
    return json.loads(FIXTURE.read_text())['shape']


class PolylineCodecTests(TestCase):
    """One decoder for both networks now — it has to survive a round trip."""

    def test_the_real_upstream_shape_decodes_to_island_geometry(self):
        points = decode_polyline(real_shape())

        self.assertGreater(len(points), 500)
        self.assertTrue(is_plausible_route_coordinates(points))
        for lat, lon in points:
            self.assertTrue(
                BBOX[0] < lat < BBOX[1] and BBOX[2] < lon < BBOX[3],
                f'{lat},{lon} is not on São Miguel',
            )

    def test_encoding_round_trips_to_within_a_metre(self):
        points = decode_polyline(real_shape())
        again = decode_polyline(encode_polyline(points))

        self.assertEqual(len(points), len(again))
        worst = max(
            haversine_km(a[0], a[1], b[0], b[1]) for a, b in zip(points, again)
        )
        self.assertLess(worst, 0.001)   # < 1 m, the 1e5 grid

    def test_empty_and_junk_decode_to_nothing_rather_than_raising(self):
        self.assertEqual(decode_polyline(''), [])
        self.assertEqual(encode_polyline([]), '')
        self.assertFalse(is_plausible_route_coordinates([]))


class GeometryFixture(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        self.operator, _ = Operator.objects.get_or_create(
            island=self.island, name='AzoresBus', defaults={'contact': {}},
        )
        self.pattern = ServicePattern.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, key='everyday',
            monday=True, tuesday=True, wednesday=True, thursday=True,
            friday=True, saturday=True, sunday=True,
        )
        self.points = decode_polyline(real_shape())

    def trip_along_shape(self, indices, *, dataset=DATASET_AZORESBUS, poles=True,
                         shape=None, code='110'):
        """A trip whose stops sit ON the real shape, at the given vertex indices."""
        line = Line.objects.create(
            island=self.island, dataset=dataset, code=code, operator=self.operator,
        )
        trip = Trip.objects.create(
            island=self.island, dataset=dataset, line=line,
            service=self.pattern, source=Trip.SOURCE_OPERATOR,
        )
        for sequence, index in enumerate(indices, start=1):
            lat, lon = self.points[index]
            # Keyed on SEQUENCE, not the vertex index: a trip may legitimately
            # touch the same point twice, and the id has to stay unique.
            stop = Stop.objects.create(
                island=self.island, dataset=dataset, name=f'STOP {sequence}',
                cleaned_name=f'stop {sequence}', latitude=lat, longitude=lon,
            )
            external = None
            if poles:
                external = ExternalStop.objects.create(
                    island=self.island, dataset=dataset,
                    external_id=f'ext-{trip.id}-{sequence}', code=f'P{sequence:02d}',
                    name=stop.name, latitude=lat, longitude=lon, stop=stop,
                )
            StopTime.objects.create(
                island=self.island, trip=trip, stop=stop, external_stop=external,
                sequence=sequence, departure_time=time(8, sequence),
            )
        if shape is not None:
            self.attach_shape(trip, shape)
        return trip

    def attach_shape(self, trip, encoded):
        from azoresbus.models import ExternalJourney

        ExternalJourney.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS,
            external_id=f'j-{trip.id}', route_ext_id='9', direction=0,
            shape=encoded, trip=trip,
        )

    def stop_times(self, trip):
        return sorted(trip.stop_times.all(), key=lambda st: st.sequence)


class TrimShapeTests(GeometryFixture):
    def test_a_trimmed_path_begins_and_ends_at_the_ride(self):
        trip = self.trip_along_shape([0, 300, 600, 915], shape=real_shape())
        board, alight = self.stop_times(trip)[1], self.stop_times(trip)[2]

        trimmed = decode_polyline(trim_shape(trip_shape(trip), board, alight))

        self.assertTrue(trimmed)
        start_gap = haversine_km(
            trimmed[0][0], trimmed[0][1], *stop_time_position(board))
        end_gap = haversine_km(
            trimmed[-1][0], trimmed[-1][1], *stop_time_position(alight))
        self.assertLess(start_gap, 0.05)   # 50 m
        self.assertLess(end_gap, 0.05)

    def test_a_trimmed_path_is_shorter_than_the_whole_trip(self):
        trip = self.trip_along_shape([0, 300, 600, 915], shape=real_shape())
        board, alight = self.stop_times(trip)[1], self.stop_times(trip)[2]

        whole = decode_polyline(trip_shape(trip))
        trimmed = decode_polyline(trim_shape(trip_shape(trip), board, alight))

        self.assertLess(len(trimmed), len(whole))
        self.assertGreater(len(trimmed), 1)

    def test_the_full_ride_keeps_essentially_the_whole_shape(self):
        trip = self.trip_along_shape([0, 300, 915], shape=real_shape())
        board, alight = self.stop_times(trip)[0], self.stop_times(trip)[-1]

        trimmed = decode_polyline(trim_shape(trip_shape(trip), board, alight))
        self.assertEqual(len(trimmed), len(self.points))

    def test_a_trip_with_no_shape_yields_nothing(self):
        trip = self.trip_along_shape([0, 300])
        board, alight = self.stop_times(trip)

        self.assertEqual(trip_shape(trip), '')
        self.assertEqual(trim_shape(trip_shape(trip), board, alight), '')

    def test_a_shape_that_does_not_match_the_stops_is_refused(self):
        """A wrong line is worse than no line — the rider believes it."""
        trip = self.trip_along_shape([0, 300], shape=real_shape())
        board, alight = self.stop_times(trip)
        # Move the stops to the far side of the island, off this route.
        for stop_time in (board, alight):
            stop_time.external_stop.latitude = 37.90
            stop_time.external_stop.longitude = -25.85
            stop_time.external_stop.save()

        self.assertEqual(trim_shape(trip_shape(trip), board, alight), '')

    def test_the_rejection_threshold_is_the_documented_one(self):
        trip = self.trip_along_shape([0, 300], shape=real_shape())
        board, alight = self.stop_times(trip)
        lat, lon = self.points[0]

        # Just inside the threshold: still trimmed.
        board.external_stop.latitude = lat + (MAX_STOP_TO_SHAPE_KM * 0.5) / 111.0
        board.external_stop.save()
        self.assertNotEqual(trim_shape(trip_shape(trip), board, alight), '')

        # Well outside it: refused.
        board.external_stop.latitude = lat + (MAX_STOP_TO_SHAPE_KM * 4) / 111.0
        board.external_stop.save()
        self.assertEqual(trim_shape(trip_shape(trip), board, alight), '')

    def test_a_ride_collapsing_onto_one_vertex_draws_nothing(self):
        trip = self.trip_along_shape([10, 10], shape=real_shape())
        board, alight = self.stop_times(trip)

        self.assertEqual(trim_shape(trip_shape(trip), board, alight), '')


class StopPositionTests(GeometryFixture):
    def test_the_pole_wins_over_the_centroid(self):
        """The centroid can sit mid-road, on neither side. The pole is where you stand."""
        trip = self.trip_along_shape([0, 300], shape=real_shape())
        board = self.stop_times(trip)[0]
        board.stop.latitude = 37.99          # deliberately wrong centroid
        board.stop.longitude = -25.99
        board.stop.save()

        self.assertEqual(
            stop_time_position(board),
            (board.external_stop.latitude, board.external_stop.longitude),
        )

    def test_the_centroid_is_used_when_there_is_no_pole(self):
        trip = self.trip_along_shape([0, 300], poles=False)
        board = self.stop_times(trip)[0]

        self.assertEqual(
            stop_time_position(board), (board.stop.latitude, board.stop.longitude),
        )


class LegGeometryTests(GeometryFixture):
    def test_it_returns_the_leg_stops_with_pole_coordinates(self):
        trip = self.trip_along_shape([0, 200, 400, 600, 915], shape=real_shape())
        times = self.stop_times(trip)
        board, alight = times[1], times[3]

        payload = leg_geometry(trip, board, alight)

        self.assertEqual([s['sequence'] for s in payload['stops']], [2, 3, 4])
        self.assertTrue(all('lat' in s and 'lon' in s for s in payload['stops']))
        self.assertTrue(all('code' in s for s in payload['stops']))
        self.assertTrue(all('stopId' in s for s in payload['stops']))
        self.assertTrue(payload['shape'])

    def test_the_stop_list_is_trimmed_to_the_ride_not_the_whole_trip(self):
        trip = self.trip_along_shape([0, 200, 400, 600, 915], shape=real_shape())
        times = self.stop_times(trip)

        payload = leg_geometry(trip, times[1], times[2])
        self.assertEqual(len(payload['stops']), 2)

    def test_legacy_yields_stops_but_no_shape_and_no_pole(self):
        trip = self.trip_along_shape(
            [0, 300], dataset=DATASET_LEGACY, poles=False, code='218',
        )
        board, alight = self.stop_times(trip)

        payload = leg_geometry(trip, board, alight)

        self.assertEqual(payload['shape'], '')
        self.assertTrue(payload['stops'])
        self.assertFalse(any('code' in s for s in payload['stops']))


class TripGeometryEndpointTests(GeometryFixture):
    """`GET /api/v3/transit/trips/{id}/geometry`."""

    HEADERS = {'HTTP_X_ISLAND': 'sao-miguel'}

    def get(self, trip_id, **params):
        from rest_framework.test import APIClient

        params.setdefault('dataset', DATASET_AZORESBUS)
        return APIClient().get(
            f'/api/v3/transit/trips/{trip_id}/geometry', params, **self.HEADERS,
        )

    def test_it_returns_the_trimmed_shape_and_the_leg_stops(self):
        trip = self.trip_along_shape([0, 200, 400, 600, 915], shape=real_shape())

        response = self.get(trip.id, **{'from': 2, 'to': 4})
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual([s['sequence'] for s in body['stops']], [2, 3, 4])
        self.assertTrue(body['shape'])
        self.assertEqual(body['tripId'], trip.id)
        self.assertEqual(body['route'], '110')

    def test_the_returned_points_are_poles_not_centroids(self):
        """A centroid can sit mid-road; a rider walks to the pole."""
        trip = self.trip_along_shape([0, 300], shape=real_shape())
        board = self.stop_times(trip)[0]
        board.stop.latitude = 37.99
        board.stop.longitude = -25.99
        board.stop.save()

        first = self.get(trip.id).json()['stops'][0]
        self.assertAlmostEqual(first['lat'], board.external_stop.latitude, places=6)
        self.assertNotAlmostEqual(first['lat'], 37.99, places=3)

    def test_omitting_the_range_returns_the_whole_trip(self):
        trip = self.trip_along_shape([0, 200, 400, 915], shape=real_shape())

        body = self.get(trip.id).json()
        self.assertEqual(len(body['stops']), 4)

    def test_a_reversed_range_is_read_the_right_way_round(self):
        trip = self.trip_along_shape([0, 200, 400, 915], shape=real_shape())

        body = self.get(trip.id, **{'from': 4, 'to': 2}).json()
        self.assertEqual([s['sequence'] for s in body['stops']], [2, 3, 4])

    def test_a_junk_range_falls_back_to_the_whole_trip_rather_than_erroring(self):
        trip = self.trip_along_shape([0, 200, 915], shape=real_shape())

        response = self.get(trip.id, **{'from': 'banana', 'to': '999'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['stops']), 3)

    def test_an_unknown_trip_is_a_404(self):
        self.assertEqual(self.get(999999).status_code, 404)

    def test_legacy_returns_stops_but_no_shape(self):
        trip = self.trip_along_shape(
            [0, 300], dataset=DATASET_LEGACY, poles=False, code='218',
        )
        from rest_framework.test import APIClient

        response = APIClient().get(
            f'/api/v3/transit/trips/{trip.id}/geometry',
            {'dataset': DATASET_LEGACY}, **self.HEADERS,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['shape'], '')
        self.assertTrue(body['stops'])

    def test_a_trip_from_the_other_dataset_is_not_reachable(self):
        """Datasets must not leak into one another (98 B4)."""
        trip = self.trip_along_shape(
            [0, 300], dataset=DATASET_LEGACY, poles=False, code='218',
        )
        self.assertEqual(self.get(trip.id).status_code, 404)
