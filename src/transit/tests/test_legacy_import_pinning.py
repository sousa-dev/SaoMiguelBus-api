"""98 B8: re-running the legacy import must not touch AzoresBus rows.

`update_or_create(island=, cleaned_name=)` and `update_or_create(island=, code=)`
are dataset-blind. Once uniqueness includes `dataset` they either raise or, worse,
update the AzoresBus row in place -- the importer would overwrite the new network
with the old one. `validate_legacy_parity` counts unfiltered and so fails
permanently the day AzoresBus lands.
"""

from __future__ import annotations

from django.test import TestCase

from tenancy.services import get_or_create_default_island
from transit.models import (
    DATASET_AZORESBUS,
    DATASET_LEGACY,
    Calendar,
    Line,
    Operator,
    Stop,
    Trip,
)
from transit.services import legacy_import
from transit.services.legacy_import import (
    QUERY_ROUTES,
    QUERY_STOPS,
    migrate_lines_trips,
    migrate_stops,
)


class StubLegacySource:
    """Minimal stand-in for LegacySource: maps a query to canned rows."""

    def __init__(self, rows_by_query: dict):
        self._rows = rows_by_query

    def fetchall(self, query: str):
        return self._rows.get(query, [])


# One legacy stop and one legacy route, both colliding with AzoresBus by name/code.
LEGACY_STOPS = [
    (1, 'PONTA DELGADA', 'ponta delgada', 37.70, -25.67),
    (2, 'RIBEIRA GRANDE', 'ribeira grande', 37.75, -25.51),
]
LEGACY_ROUTES = [
    (
        10,                       # legacy id
        '101',                    # route code -- collides with AzoresBus
        "{'PONTA DELGADA': '08h00', 'RIBEIRA GRANDE': '08h30'}",
        'WEEKDAY',
        None, 0, 0, 0,
    ),
]


class LegacyImportPinningTests(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        for service_type in (Calendar.WEEKDAY, Calendar.SATURDAY, Calendar.SUNDAY):
            Calendar.objects.get_or_create(
                island=self.island, service_type=service_type,
            )
        # infer_operator_name('101') returns 'Other' for unrecognised prefixes.
        for name in ('Other', 'CRP', 'AzoresBus'):
            Operator.objects.get_or_create(
                island=self.island, name=name, defaults={'contact': {}},
            )

        # The AzoresBus network already exists, sharing a code and a stop name.
        azb_operator = Operator.objects.get(island=self.island, name='AzoresBus')
        self.azb_line = Line.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, code='101',
            operator=azb_operator, display_name='AzoresBus 101',
        )
        self.azb_stop = Stop.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS,
            name='PONTA DELGADA', cleaned_name='ponta delgada',
            latitude=37.99, longitude=-25.99,
        )

        self.source = StubLegacySource({
            QUERY_STOPS: LEGACY_STOPS,
            QUERY_ROUTES: LEGACY_ROUTES,
        })

    def _run_import(self):
        migrate_stops(self.island, self.source)
        migrate_lines_trips(self.island, self.source)

    def test_import_twice_leaves_azoresbus_rows_untouched(self):
        for _ in range(2):
            self._run_import()

        self.azb_line.refresh_from_db()
        self.azb_stop.refresh_from_db()

        self.assertEqual(self.azb_line.display_name, 'AzoresBus 101')
        self.assertEqual(self.azb_line.operator.name, 'AzoresBus')
        self.assertEqual(self.azb_stop.latitude, 37.99)
        self.assertEqual(
            self.azb_stop.longitude, -25.99,
            'the legacy importer overwrote an AzoresBus stop (98 B8)',
        )

    def test_import_writes_only_legacy_rows(self):
        self._run_import()

        self.assertTrue(
            all(
                stop.dataset == DATASET_LEGACY
                for stop in Stop.objects.exclude(pk=self.azb_stop.pk)
            )
        )
        self.assertEqual(
            Line.objects.filter(code='101', dataset=DATASET_LEGACY).count(), 1,
        )
        self.assertEqual(
            Line.objects.filter(code='101', dataset=DATASET_AZORESBUS).count(), 1,
        )
        self.assertTrue(
            all(trip.dataset == DATASET_LEGACY for trip in Trip.objects.all())
        )

    def test_import_is_idempotent_across_runs(self):
        self._run_import()
        first = (Stop.objects.count(), Line.objects.count(), Trip.objects.count())
        self._run_import()
        self.assertEqual(
            (Stop.objects.count(), Line.objects.count(), Trip.objects.count()),
            first,
            'a second import duplicated rows',
        )

    def test_parity_command_counts_only_legacy(self):
        """Unfiltered counts would include AzoresBus rows and never match."""
        self._run_import()

        legacy_stops = Stop.objects.filter(dataset=DATASET_LEGACY).count()
        self.assertEqual(legacy_stops, len(LEGACY_STOPS))
        self.assertNotEqual(
            legacy_stops, Stop.objects.count(),
            'fixture is not exercising the mixed-network case',
        )
