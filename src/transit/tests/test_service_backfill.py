"""Legacy trips must gain a ServicePattern equivalent to their Calendar.

S3 resolves "does this trip run on this ISO date?" through `Trip.service`. If
legacy trips have only a `Calendar`, they become invisible the moment search
stops filtering on `calendar__service_type` -- which would delete the entire
outgoing network from the app on the day S3 deploys.

The mapping (02 section 3.3):
    WEEKDAY  -> Mon-Fri true, unbounded
    SATURDAY -> Sat
    SUNDAY   -> Sun
"""

from __future__ import annotations

from django.test import TestCase

from tenancy.services import get_or_create_default_island
from transit.models import (
    DATASET_LEGACY,
    Calendar,
    Line,
    Operator,
    ServicePattern,
    Trip,
)


EXPECTED_MASK = {
    Calendar.WEEKDAY: {
        'monday': True, 'tuesday': True, 'wednesday': True,
        'thursday': True, 'friday': True, 'saturday': False, 'sunday': False,
    },
    Calendar.SATURDAY: {
        'monday': False, 'tuesday': False, 'wednesday': False,
        'thursday': False, 'friday': False, 'saturday': True, 'sunday': False,
    },
    Calendar.SUNDAY: {
        'monday': False, 'tuesday': False, 'wednesday': False,
        'thursday': False, 'friday': False, 'saturday': False, 'sunday': True,
    },
}


class LegacyServiceBackfillTests(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        operator, _ = Operator.objects.get_or_create(
            island=self.island, name='CRP', defaults={'contact': {}},
        )
        self.line, _ = Line.objects.get_or_create(
            island=self.island, dataset=DATASET_LEGACY, code='BACKFILL',
            defaults={'operator': operator},
        )
        self.trips = {}
        for service_type in EXPECTED_MASK:
            calendar, _ = Calendar.objects.get_or_create(
                island=self.island, service_type=service_type,
            )
            self.trips[service_type] = Trip.objects.create(
                island=self.island, dataset=DATASET_LEGACY,
                line=self.line, calendar=calendar,
                source=Trip.SOURCE_OPERATOR,
            )

    def test_backfill_gives_every_legacy_trip_a_service_pattern(self):
        from transit.services.service_backfill import backfill_legacy_services

        backfill_legacy_services(self.island)

        for service_type, trip in self.trips.items():
            trip.refresh_from_db()
            self.assertIsNotNone(
                trip.service,
                f'{service_type} trip has no ServicePattern after back-fill',
            )
            for field, expected in EXPECTED_MASK[service_type].items():
                self.assertEqual(
                    getattr(trip.service, field), expected,
                    f'{service_type}.{field} should be {expected}',
                )

    def test_backfilled_patterns_are_unbounded_and_official(self):
        """Legacy service is what we already shipped, not an inference."""
        from transit.services.service_backfill import backfill_legacy_services

        backfill_legacy_services(self.island)

        trip = self.trips[Calendar.WEEKDAY]
        trip.refresh_from_db()
        self.assertIsNone(trip.service.start_date)
        self.assertIsNone(trip.service.end_date)
        self.assertFalse(trip.service.end_unknown)
        self.assertEqual(
            trip.service.confidence, ServicePattern.CONFIDENCE_OFFICIAL,
        )

    def test_trips_sharing_a_calendar_share_one_pattern(self):
        from transit.services.service_backfill import backfill_legacy_services

        extra = Trip.objects.create(
            island=self.island, dataset=DATASET_LEGACY, line=self.line,
            calendar=self.trips[Calendar.WEEKDAY].calendar,
            source=Trip.SOURCE_OPERATOR,
        )
        backfill_legacy_services(self.island)

        extra.refresh_from_db()
        self.trips[Calendar.WEEKDAY].refresh_from_db()
        self.assertEqual(
            extra.service_id, self.trips[Calendar.WEEKDAY].service_id,
        )
        self.assertEqual(
            ServicePattern.objects.filter(
                island=self.island, dataset=DATASET_LEGACY,
            ).count(),
            3,
            'one pattern per legacy day-type, not one per trip',
        )

    def test_backfill_is_idempotent(self):
        from transit.services.service_backfill import backfill_legacy_services

        backfill_legacy_services(self.island)
        first = set(
            ServicePattern.objects.filter(island=self.island)
            .values_list('id', flat=True)
        )
        backfill_legacy_services(self.island)
        second = set(
            ServicePattern.objects.filter(island=self.island)
            .values_list('id', flat=True)
        )
        self.assertEqual(first, second, 'a second run churned the patterns')

    def test_backfill_leaves_calendar_in_place(self):
        """Calendar stays readable so nothing breaks mid-migration."""
        from transit.services.service_backfill import backfill_legacy_services

        backfill_legacy_services(self.island)

        for trip in self.trips.values():
            trip.refresh_from_db()
            self.assertIsNotNone(trip.calendar)
