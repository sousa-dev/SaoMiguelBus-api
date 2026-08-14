"""S3: which network a request resolves to, and when that flips.

The cutover lives on the server (00 Decision 1). A build installed in June gets
correct September timetables because it never had the decision to make: it sends
no `dataset`, and the server resolves one from the Atlantic/Azores date.

Every shipped client collapses the date to a day-type BEFORE the request
(lib/transit-format.ts resolveDayType, src/lib/format.ts, the legacy PWA), so
`day=weekday` with no date is the normal case and dataset resolution falls back
to the server's own date.
"""

from __future__ import annotations

from datetime import date, datetime, timezone as dt_timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase

from tenancy.services import get_or_create_default_island
from transit.models import DATASET_AZORESBUS, DATASET_LEGACY, Line, Operator, Trip
from transit.services.schedule_phase import (
    AZORES,
    resolve_dataset,
    schedule_phase,
)


CUTOVER = '2026-09-01T00:00:00+00:00'
BANNER_UNTIL = '2026-10-01T00:00:00+00:00'


def azores_instant(text: str) -> datetime:
    """A wall-clock time in Atlantic/Azores, as an aware instant."""
    return datetime.fromisoformat(text).replace(tzinfo=AZORES)


class DatasetResolutionTests(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        self.island.feature_flags = {
            **(self.island.feature_flags or {}),
            'azoresbus': {'cutoverAt': CUTOVER, 'bannerUntil': BANNER_UNTIL},
        }
        self.island.save(update_fields=['feature_flags'])
        self._give_azoresbus_data()

    def _give_azoresbus_data(self):
        operator, _ = Operator.objects.get_or_create(
            island=self.island, name='AzoresBus', defaults={'contact': {}},
        )
        line = Line.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, code='101',
            operator=operator,
        )
        Trip.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, line=line,
            source=Trip.SOURCE_OPERATOR,
        )

    def _at(self, text: str) -> str:
        with patch('transit.services.schedule_phase.timezone.now',
                   return_value=azores_instant(text).astimezone(dt_timezone.utc)):
            return resolve_dataset(self.island)

    # -- the instant, in the right timezone ---------------------------------

    def test_one_minute_before_azores_midnight_is_legacy(self):
        self.assertEqual(self._at('2026-08-31T23:59'), DATASET_LEGACY)

    def test_one_minute_after_azores_midnight_is_azoresbus(self):
        self.assertEqual(self._at('2026-09-01T00:01'), DATASET_AZORESBUS)

    def test_the_flip_uses_azores_local_time_not_utc(self):
        """Atlantic/Azores is UTC+0 in summer (DST) and UTC-1 in winter.

        On 1 September the two coincide, so that date cannot prove the
        conversion happens. A WINTER cutover can: local midnight is 01:00 UTC,
        so a naive UTC comparison would flip a full hour early.
        """
        self.island.feature_flags = {
            'azoresbus': {'cutoverAt': '2027-01-01T00:00:00-01:00'},
        }
        self.island.save(update_fields=['feature_flags'])

        # 00:30 UTC == 2026-12-31 23:30 in the Azores: still before the cutover.
        with patch(
            'transit.services.schedule_phase.timezone.now',
            return_value=datetime(2027, 1, 1, 0, 30, tzinfo=dt_timezone.utc),
        ):
            self.assertEqual(resolve_dataset(self.island), DATASET_LEGACY)

        # 01:30 UTC == 2027-01-01 00:30 in the Azores: past it.
        with patch(
            'transit.services.schedule_phase.timezone.now',
            return_value=datetime(2027, 1, 1, 1, 30, tzinfo=dt_timezone.utc),
        ):
            self.assertEqual(resolve_dataset(self.island), DATASET_AZORESBUS)

    # -- explicit override ---------------------------------------------------

    def test_an_explicit_request_wins(self):
        with patch('transit.services.schedule_phase.timezone.now',
                   return_value=azores_instant('2026-08-15T12:00')):
            self.assertEqual(
                resolve_dataset(self.island, requested=DATASET_AZORESBUS),
                DATASET_AZORESBUS,
            )

    def test_a_nonsense_override_is_ignored_not_honoured(self):
        with patch('transit.services.schedule_phase.timezone.now',
                   return_value=azores_instant('2026-09-15T12:00')):
            self.assertEqual(
                resolve_dataset(self.island, requested='not-a-dataset'),
                DATASET_AZORESBUS,
            )

    # -- an explicit date beats the clock -----------------------------------

    def test_a_requested_date_decides_when_one_is_given(self):
        with patch('transit.services.schedule_phase.timezone.now',
                   return_value=azores_instant('2026-08-15T12:00')):
            self.assertEqual(
                resolve_dataset(self.island, on_date=date(2026, 9, 15)),
                DATASET_AZORESBUS,
            )

    # -- the safety net ------------------------------------------------------

    def test_falls_back_to_legacy_when_the_new_network_is_empty(self):
        """Deploying the cutover before a sync must not empty the app."""
        Trip.objects.filter(
            island=self.island, dataset=DATASET_AZORESBUS,
        ).delete()

        with patch('transit.services.schedule_phase.timezone.now',
                   return_value=azores_instant('2026-09-15T12:00')):
            self.assertEqual(resolve_dataset(self.island), DATASET_LEGACY)

    def test_no_cutover_configured_means_legacy_forever(self):
        self.island.feature_flags = {'azoresbus': {}}
        self.island.save(update_fields=['feature_flags'])

        with patch('transit.services.schedule_phase.timezone.now',
                   return_value=azores_instant('2027-01-01T12:00')):
            self.assertEqual(resolve_dataset(self.island), DATASET_LEGACY)


class PhaseTests(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        self.island.feature_flags = {
            'azoresbus': {'cutoverAt': CUTOVER, 'bannerUntil': BANNER_UNTIL},
        }
        self.island.save(update_fields=['feature_flags'])

    def _phase(self, text):
        return schedule_phase(self.island, at=azores_instant(text))

    def test_before_cutover_is_preview(self):
        self.assertEqual(self._phase('2026-08-20T10:00'), 'preview')

    def test_between_cutover_and_banner_end_is_live(self):
        self.assertEqual(self._phase('2026-09-15T10:00'), 'live')

    def test_after_the_banner_retires_is_settled(self):
        self.assertEqual(self._phase('2026-10-02T10:00'), 'settled')

    def test_the_boundaries_are_instants_not_dates(self):
        self.assertEqual(self._phase('2026-08-31T23:59'), 'preview')
        self.assertEqual(self._phase('2026-09-01T00:00'), 'live')
