"""End-to-end import: captured payloads -> transit rows.

Driven entirely by the committed fixtures, so it exercises the real shapes
without touching the network. The cases that matter are the ones 98 says the
naive importer gets wrong: isActive is a display flag, night times wrap, poles
collapse but must stay recoverable, and legacy rows must not be touched.
"""

from __future__ import annotations

import json
from datetime import date, time
from pathlib import Path

from django.test import TestCase

from azoresbus.models import ExternalJourney, ExternalStop, ServiceObservation, SyncRun
from azoresbus.services_import import import_schedules
from tenancy.services import for_island, get_or_create_default_island
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


FIXTURES = Path(__file__).parent / 'fixtures'

ROUTES = {'1': '101', '2': '102', '9': '112', '25': '301',
          '31': '307', '48': '335', '53': 'N03'}
TERM_WEEK = [date(2026, 9, day) for day in range(14, 21)]
SAMPLE_DATES = TERM_WEEK + [date(2026, 9, 2), date(2027, 7, 12)]
HOLIDAYS = {date(2026, 12, 8)}

DETAIL_FILES = {
    '984': '53', '1009': '2', '1011': '2',
    '633': '31', '645': '31', '647': '31', '661': '31', '662': '31',
    '236': '9', '237': '9', '488': '25', '950': '48',
}


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


def captured_payloads():
    journeys = {}
    for route_id in ROUTES:
        for day in SAMPLE_DATES:
            journeys[(route_id, day)] = load(
                f'journeys_{route_id}_{day.isoformat()}.json'
            )
    details = {
        jid: load(f'journey_{rid}_{jid}.json')
        for jid, rid in DETAIL_FILES.items()
    }
    return {
        'stops': load('stops.json'),
        'routes': load('routes.json'),
        'journeys': journeys,
        'details': details,
        'sampled_dates': SAMPLE_DATES,
        'holidays': HOLIDAYS,
    }


class ImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.island = get_or_create_default_island()
        # A legacy row that shares a line code and a stop name with the import.
        operator, _ = Operator.objects.get_or_create(
            island=cls.island, name='CRP', defaults={'contact': {}},
        )
        cls.legacy_line = Line.objects.create(
            island=cls.island, dataset=DATASET_LEGACY, code='101',
            operator=operator, display_name='legacy 101',
        )
        cls.legacy_stop = Stop.objects.create(
            island=cls.island, dataset=DATASET_LEGACY,
            name='PONTA DELGADA (ALFÂNDEGA)',
            cleaned_name='ponta delgada (alfandega)',
            latitude=1.0, longitude=2.0,
        )
        with for_island(cls.island):
            cls.sync_run = SyncRun.objects.create(
                island=cls.island, kind=SyncRun.KIND_SCHEDULES,
            )
            cls.report = import_schedules(
                cls.island, run=cls.sync_run, **captured_payloads()
            )

    # -- shape --------------------------------------------------------------

    def test_all_55_routes_become_lines(self):
        """98 B5: isActive is a display flag. Honouring it drops 328 entirely."""
        self.assertEqual(
            Line.objects.filter(
                island=self.island, dataset=DATASET_AZORESBUS,
            ).count(),
            55,
        )

    def test_stops_collapse_to_816_with_poles_kept(self):
        self.assertEqual(
            Stop.objects.filter(
                island=self.island, dataset=DATASET_AZORESBUS,
            ).count(),
            816,
        )
        self.assertEqual(
            ExternalStop.objects.filter(island=self.island).count(), 1456,
        )

    def test_every_external_stop_points_at_its_collapsed_stop(self):
        sample = ExternalStop.objects.filter(island=self.island).first()
        self.assertEqual(sample.stop.name, sample.name)
        self.assertEqual(sample.stop.dataset, DATASET_AZORESBUS)

    def test_azoresbus_lines_get_their_own_operator(self):
        """infer_operator_name would file all 55 under 'Other' (02 §3.8)."""
        line = Line.objects.get(
            island=self.island, dataset=DATASET_AZORESBUS, code='101',
        )
        self.assertEqual(line.operator.name, 'AzoresBus')

    # -- isolation ----------------------------------------------------------

    def test_legacy_rows_are_untouched(self):
        self.legacy_line.refresh_from_db()
        self.legacy_stop.refresh_from_db()
        self.assertEqual(self.legacy_line.display_name, 'legacy 101')
        self.assertEqual(self.legacy_stop.latitude, 1.0)

    def test_both_101s_coexist(self):
        self.assertEqual(
            Line.objects.filter(island=self.island, code='101').count(), 2,
        )

    # -- calendar -----------------------------------------------------------

    def test_112_trips_run_tuesday_and_thursday_only(self):
        journey = ExternalJourney.objects.get(
            island=self.island, external_id='236',
        )
        pattern = journey.trip.service
        self.assertTrue(pattern.tuesday)
        self.assertTrue(pattern.thursday)
        self.assertFalse(pattern.monday)
        self.assertFalse(pattern.wednesday)
        self.assertFalse(pattern.friday)

    def test_307_school_extras_are_bounded_to_term(self):
        journey = ExternalJourney.objects.get(
            island=self.island, external_id='633',
        )
        self.assertEqual(journey.trip.service.start_date, date(2026, 9, 14))
        self.assertEqual(
            journey.trip.service.confidence, ServicePattern.CONFIDENCE_SAMPLED,
        )

    def test_identical_rules_share_one_pattern(self):
        a = ExternalJourney.objects.get(island=self.island, external_id='236')
        b = ExternalJourney.objects.get(island=self.island, external_id='237')
        self.assertEqual(a.trip.service_id, b.trip.service_id)

    def test_observations_are_recorded_for_the_audit_trail(self):
        observed = ServiceObservation.objects.filter(
            island=self.island, external_id='236',
        ).values_list('date', flat=True)
        self.assertEqual(
            set(observed), {date(2026, 9, 15), date(2026, 9, 17)},
        )

    # -- the wrap (98 B2) ---------------------------------------------------

    def test_n03_984_stop_times_carry_the_day_offset(self):
        journey = ExternalJourney.objects.get(
            island=self.island, external_id='984',
        )
        rows = {
            st.sequence: st
            for st in StopTime.objects.filter(trip=journey.trip)
        }
        self.assertEqual(rows[42].day_offset, 0)
        self.assertEqual(rows[42].departure_time, time(23, 59, 1))
        self.assertEqual(rows[43].day_offset, 1)
        self.assertEqual(rows[43].departure_time, time(0, 0))
        self.assertEqual(rows[47].day_offset, 1)

    def test_ordering_by_sequence_survives_the_wrap(self):
        journey = ExternalJourney.objects.get(
            island=self.island, external_id='984',
        )
        rows = list(
            StopTime.objects.filter(trip=journey.trip).order_by('sequence')
        )
        keyed = sorted(rows, key=lambda r: (r.day_offset, r.departure_time))
        self.assertEqual([r.sequence for r in rows], [r.sequence for r in keyed])

    # -- poles --------------------------------------------------------------

    def test_stop_times_record_which_pole_was_served(self):
        journey = ExternalJourney.objects.get(
            island=self.island, external_id='488',
        )
        rows = StopTime.objects.filter(trip=journey.trip)
        self.assertTrue(rows.exists())
        self.assertTrue(
            all(row.external_stop_id is not None for row in rows),
            'collapsing to 816 names destroyed the side-of-road information',
        )

    # -- idempotency --------------------------------------------------------

    def test_a_second_import_writes_no_duplicates(self):
        with for_island(self.island):
            before = (
                Stop.objects.filter(dataset=DATASET_AZORESBUS).count(),
                Line.objects.filter(dataset=DATASET_AZORESBUS).count(),
                Trip.objects.filter(dataset=DATASET_AZORESBUS).count(),
                StopTime.objects.count(),
            )
            run = SyncRun.objects.create(
                island=self.island, kind=SyncRun.KIND_SCHEDULES,
            )
            import_schedules(self.island, run=run, **captured_payloads())
            after = (
                Stop.objects.filter(dataset=DATASET_AZORESBUS).count(),
                Line.objects.filter(dataset=DATASET_AZORESBUS).count(),
                Trip.objects.filter(dataset=DATASET_AZORESBUS).count(),
                StopTime.objects.count(),
            )
        self.assertEqual(before, after)

    def test_report_counts_are_populated(self):
        self.assertEqual(self.report['stops'], 816)
        self.assertEqual(self.report['lines'], 55)
        self.assertGreater(self.report['trips'], 0)
        self.assertGreater(self.report['journey_count'], 0)
        self.assertEqual(len(self.report['flagged_stop_groups']), 14)
