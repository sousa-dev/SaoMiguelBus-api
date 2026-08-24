"""The one-time rename of AzoresBus stops must not orphan or duplicate anything.

`Stop` has no upstream id, so `cleaned_name` is its identity, and nothing in
this codebase prunes stops. Getting this wrong does not raise -- it silently
leaves half the StopTimes pointing at a stranded row and breaks every saved
favourite and Hub deep link at the same time.
"""

from __future__ import annotations

from datetime import time

from importlib import import_module

from django.apps import apps as django_apps
from django.test import TestCase

from atlas.models import AtlasCategory, AtlasPoi
from azoresbus.models import ExternalStop
from tenancy.services import get_or_create_default_island
from transit.models import (
    DATASET_AZORESBUS,
    Line,
    Operator,
    ServicePattern,
    Stop,
    StopAlias,
    StopTime,
    Trip,
)

# Numeric module name, so it cannot be a plain `from ... import`.
MIGRATION = import_module(
    'transit.migrations.0010_canonicalize_azoresbus_stop_names',
)


class MigrationFixture(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        self.operator = Operator.objects.create(
            island=self.island, name='AzoresBus', contact={},
        )
        self.pattern = ServicePattern.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, key='everyday',
            monday=True, tuesday=True, wednesday=True, thursday=True,
            friday=True, saturday=True, sunday=True,
        )
        self.line = Line.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS,
            operator=self.operator, code='101',
        )

    def make_stop(self, name, cleaned, *, lat=37.74, lon=-25.67, code='1000'):
        stop = Stop.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS,
            name=name, cleaned_name=cleaned, latitude=lat, longitude=lon,
        )
        ExternalStop.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS,
            external_id=code, code=code, name=name,
            latitude=lat, longitude=lon, stop=stop,
        )
        return stop

    def make_trip_through(self, *stops):
        trip = Trip.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, line=self.line,
            source=Trip.SOURCE_OPERATOR, service=self.pattern,
        )
        for sequence, stop in enumerate(stops):
            StopTime.objects.create(
                island=self.island, trip=trip, stop=stop,
                sequence=sequence, departure_time=time(8, sequence),
            )
        return trip

    def run_migration(self):
        MIGRATION.canonicalize_stop_names(django_apps, None)


class RenameInPlaceTests(MigrationFixture):
    def test_the_stop_is_renamed_without_changing_its_pk(self):
        """`Stop.pk` is what favourites, deep links and AtlasPoi are built on."""
        stop = self.make_stop(
            'P. DELGADA (LG. ALM. DUNN)', 'p. delgada (lg. alm. dunn)', code='1030',
        )
        original_pk = stop.pk

        self.run_migration()

        stop.refresh_from_db()
        self.assertEqual(stop.pk, original_pk)
        self.assertEqual(stop.name, 'Ponta Delgada (Largo Almirante Dunn)')
        self.assertEqual(stop.cleaned_name, 'ponta delgada (largo almirante dunn)')
        self.assertEqual(Stop.objects.filter(dataset=DATASET_AZORESBUS).count(), 1)

    def test_stop_times_are_never_split_across_a_stray_row(self):
        origin = self.make_stop('S. ROQUE (IGREJA)', 's. roque (igreja)', code='1100')
        destination = self.make_stop('ACHADINHA', 'achadinha', code='1200')
        trip = self.make_trip_through(origin, destination)

        self.run_migration()

        stops = list(
            StopTime.objects.filter(trip=trip).order_by('sequence')
            .values_list('stop__name', flat=True),
        )
        self.assertEqual(stops, ['São Roque (Igreja)', 'Achadinha'])

    def test_the_old_name_becomes_an_alias(self):
        self.make_stop('V. DO NORDESTE (TERMINAL)', 'v. do nordeste (terminal)',
                       code='6001')
        self.run_migration()

        alias = StopAlias.objects.get(cleaned_alias='v. do nordeste (terminal)')
        self.assertEqual(alias.stop.name, 'Vila do Nordeste (Terminal)')

    def test_an_unchanged_name_gets_no_alias(self):
        self.make_stop('Achadinha', 'achadinha', code='1200')
        self.run_migration()
        self.assertEqual(StopAlias.objects.count(), 0)


class MergeTests(MigrationFixture):
    """`S. ROQUE (BARRACUDA)` and `SÃO ROQUE (BARRACUDA)` are one stop 15 m wide."""

    def setUp(self):
        super().setUp()
        self.first = self.make_stop(
            'S. ROQUE (BARRACUDA)', 's. roque (barracuda)',
            lat=37.75176, lon=-25.62602, code='1654',
        )
        self.second = self.make_stop(
            'SÃO ROQUE (BARRACUDA)', 'sao roque (barracuda)',
            lat=37.75164, lon=-25.62594, code='1734',
        )

    def test_the_two_rows_become_one(self):
        self.run_migration()
        survivors = Stop.objects.filter(dataset=DATASET_AZORESBUS)
        self.assertEqual(survivors.count(), 1)
        self.assertEqual(survivors.first().name, 'São Roque (Barracuda)')

    def test_stop_times_from_both_rows_survive_the_merge(self):
        """`StopTime.stop` is PROTECT -- repointing must precede the delete."""
        trip_a = self.make_trip_through(self.first)
        trip_b = self.make_trip_through(self.second)

        self.run_migration()

        survivor = Stop.objects.get(dataset=DATASET_AZORESBUS)
        self.assertEqual(StopTime.objects.filter(stop=survivor).count(), 2)
        for trip in (trip_a, trip_b):
            self.assertEqual(StopTime.objects.filter(trip=trip).count(), 1)

    def test_both_poles_survive_and_point_at_the_survivor(self):
        self.run_migration()
        survivor = Stop.objects.get(dataset=DATASET_AZORESBUS)
        self.assertEqual(ExternalStop.objects.count(), 2)
        self.assertEqual(ExternalStop.objects.filter(stop=survivor).count(), 2)

    def test_both_old_names_resolve_afterwards(self):
        self.run_migration()
        survivor = Stop.objects.get(dataset=DATASET_AZORESBUS)
        aliases = set(StopAlias.objects.values_list('cleaned_alias', flat=True))
        self.assertIn('s. roque (barracuda)', aliases)
        for alias in StopAlias.objects.all():
            self.assertEqual(alias.stop_id, survivor.pk)


class AtlasPoiTests(MigrationFixture):
    """`atlas/importers/base.py` tombstones POIs whose source_ref disappears.

    It also sets description/media/tips on CREATE only, so a tombstone-and-
    recreate silently discards every enrichment along with the deep link.
    """

    def test_the_poi_follows_the_rename(self):
        stop = self.make_stop(
            'P. DELGADA (MARINA)', 'p. delgada (marina)', code='1040',
        )
        category, _ = AtlasCategory.objects.get_or_create(
            island=self.island, slug='bus-stop',
            defaults={'group': AtlasCategory.GROUP_TRANSPORT,
                      'name': {'pt': 'Paragem', 'en': 'Bus stop'}},
        )
        poi = AtlasPoi.objects.create(
            island=self.island, source=AtlasPoi.SOURCE_TRANSIT,
            source_ref=stop.cleaned_name, name={'pt': stop.name},
            category=category,
            latitude=stop.latitude, longitude=stop.longitude,
        )
        original_uid = poi.uid

        self.run_migration()

        poi.refresh_from_db()
        self.assertEqual(poi.source_ref, 'ponta delgada (marina)')
        self.assertEqual(poi.uid, original_uid)


class IdempotencyTests(MigrationFixture):
    def test_running_twice_changes_nothing(self):
        self.make_stop('P. DELGADA (MARINA)', 'p. delgada (marina)', code='1040')
        self.make_stop('S. ROQUE (BARRACUDA)', 's. roque (barracuda)', code='1654')
        self.make_stop('SÃO ROQUE (BARRACUDA)', 'sao roque (barracuda)', code='1734')

        self.run_migration()
        first = sorted(
            Stop.objects.values_list('pk', 'name', 'cleaned_name'),
        )
        first_aliases = sorted(StopAlias.objects.values_list('cleaned_alias', 'stop_id'))

        self.run_migration()

        self.assertEqual(
            sorted(Stop.objects.values_list('pk', 'name', 'cleaned_name')), first,
        )
        self.assertEqual(
            sorted(StopAlias.objects.values_list('cleaned_alias', 'stop_id')),
            first_aliases,
        )

    def test_an_empty_dataset_is_a_noop(self):
        self.run_migration()
        self.assertEqual(Stop.objects.count(), 0)
