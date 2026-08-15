"""AzoresBus trips must not crash the v1 offline bundle (02 section 7.3).

`_trip_to_load_route` dereferenced `trip.calendar` to fill the legacy `weekday`
field. AzoresBus trips carry a ServicePattern and no Calendar, so once
`resolve_dataset` starts returning azoresbus the v1 bundle would have raised
AttributeError and 500'd -- for every ALREADY-INSTALLED build, on the one day it
must not. Those clients have no v2 endpoint to fall back to.

The projection onto three day-types is lossy by design: a v1 client cannot see
that line 112 runs Tuesday and Thursday only. It gets the coarsest true bucket,
and the v2 bundle carries the real service calendar.
"""

from __future__ import annotations

from datetime import time

from django.test import TestCase

from tenancy.services import for_island, get_or_create_default_island
from transit.models import (
    DATASET_AZORESBUS,
    Calendar,
    Line,
    Operator,
    ServicePattern,
    Stop,
    StopTime,
    Trip,
)
from transit.services.compat import legacy_day_type_for_trip
from transit.services.offline_bundle import build_offline_bundle


class LegacyDayTypeProjectionTests(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        self.operator, _ = Operator.objects.get_or_create(
            island=self.island, name='AzoresBus', defaults={'contact': {}},
        )

    def _trip(self, key: str, **days) -> Trip:
        pattern = ServicePattern.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, key=key, **days,
        )
        line = Line.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, code=f'L{key}',
            operator=self.operator,
        )
        return Trip.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, line=line,
            calendar=None, service=pattern, source=Trip.SOURCE_OPERATOR,
        )

    def test_a_weekday_service_projects_to_weekday(self):
        trip = self._trip('w', monday=True, tuesday=True, wednesday=True,
                          thursday=True, friday=True)
        self.assertEqual(legacy_day_type_for_trip(trip), 'WEEKDAY')

    def test_a_partial_week_service_still_projects_to_weekday(self):
        """Line 112 is Tuesday/Thursday only — lossy, but true and visible."""
        trip = self._trip('tt', tuesday=True, thursday=True)
        self.assertEqual(legacy_day_type_for_trip(trip), 'WEEKDAY')

    def test_a_saturday_only_service_is_not_advertised_as_a_weekday(self):
        trip = self._trip('sat', saturday=True)
        self.assertEqual(legacy_day_type_for_trip(trip), 'SATURDAY')

    def test_a_sunday_only_service_projects_to_sunday(self):
        trip = self._trip('sun', sunday=True)
        self.assertEqual(legacy_day_type_for_trip(trip), 'SUNDAY')

    def test_a_weekend_loop_prefers_saturday_over_sunday(self):
        """328 is a weekend loop; either bucket is defensible, one must be picked."""
        trip = self._trip('wknd', saturday=True, sunday=True)
        self.assertEqual(legacy_day_type_for_trip(trip), 'SATURDAY')

    def test_a_trip_with_neither_calendar_nor_service_does_not_crash(self):
        line = Line.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, code='ORPHAN',
            operator=self.operator,
        )
        trip = Trip.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, line=line,
            calendar=None, service=None, source=Trip.SOURCE_OPERATOR,
        )
        self.assertEqual(legacy_day_type_for_trip(trip), 'WEEKDAY')

    def test_a_legacy_trip_keeps_its_calendar(self):
        calendar, _ = Calendar.objects.get_or_create(
            island=self.island, service_type=Calendar.SATURDAY,
        )
        line = Line.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, code='LEG',
            operator=self.operator,
        )
        trip = Trip.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, line=line,
            calendar=calendar, source=Trip.SOURCE_OPERATOR,
        )
        self.assertEqual(legacy_day_type_for_trip(trip), 'SATURDAY')

    def test_the_v1_bundle_builds_for_an_azoresbus_network(self):
        """The regression that matters: this raised AttributeError before."""
        trip = self._trip('bundle', monday=True, tuesday=True, wednesday=True,
                          thursday=True, friday=True)
        stop = Stop.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, name='ALFA',
            cleaned_name='alfa', latitude=37.7, longitude=-25.6,
        )
        StopTime.objects.create(
            island=self.island, trip=trip, stop=stop, sequence=1,
            departure_time=time(8, 0), day_offset=0,
        )

        self.island.feature_flags = {
            **(self.island.feature_flags or {}),
            'azoresbus': {'cutoverAt': '2020-01-01T00:00:00+00:00'},
        }
        self.island.save(update_fields=['feature_flags'])

        with for_island(self.island):
            bundle = build_offline_bundle(self.island)

        routes = [row for row in bundle['routes'] if row['id'] == trip.id]
        self.assertEqual(len(routes), 1, 'the AzoresBus trip is missing from the bundle')
        self.assertEqual(routes[0]['weekday'], 'WEEKDAY')
