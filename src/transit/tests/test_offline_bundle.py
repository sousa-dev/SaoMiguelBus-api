"""Tests for the offline bundle serializer and data-revision staleness signal."""

from __future__ import annotations

from datetime import time

from django.test import TestCase

from tenancy.services import for_island
from transit.models import Stop, StopTime
from transit.services.offline_bundle import (
    bump_data_revision,
    build_offline_bundle,
    compute_bundle_version,
    get_data_revision,
    suppress_revision_bumps,
)
from transit.tests.fixtures import ensure_transit_fixtures


class OfflineBundleServiceTests(TestCase):
    def setUp(self):
        self.island, self.trip, self.line = ensure_transit_fixtures()

    def _revision(self) -> int:
        self.island.refresh_from_db()
        return get_data_revision(self.island)

    def test_bundle_has_expected_shape(self):
        with for_island(self.island):
            bundle = build_offline_bundle(self.island)
        for key in ('version', 'generatedAt', 'island', 'maps', 'counts', 'stops', 'holidays', 'infos', 'routes'):
            self.assertIn(key, bundle)
        self.assertEqual(bundle['island'], 'sao-miguel')
        self.assertGreater(len(bundle['routes']), 0)
        self.assertGreater(bundle['counts']['stops'], 0)

    def test_schedule_edit_bumps_revision(self):
        before = self._revision()
        stop = Stop.objects.create(
            island=self.island,
            name='Lagoa',
            cleaned_name='lagoa',
            latitude=37.74,
            longitude=-25.57,
        )
        after_create = self._revision()
        self.assertGreater(after_create, before)

        StopTime.objects.create(
            island=self.island,
            trip=self.trip,
            stop=stop,
            sequence=3,
            departure_time=time(10, 0),
        )
        self.assertGreater(self._revision(), after_create)

    def test_vote_does_not_bump_revision(self):
        before = self._revision()
        self.trip.likes += 1
        self.trip.save(update_fields=['likes'])
        self.assertEqual(self._revision(), before)

        self.trip.dislikes += 1
        self.trip.save(update_fields=['dislikes'])
        self.assertEqual(self._revision(), before)

    def test_delete_bumps_revision(self):
        before = self._revision()
        StopTime.objects.filter(trip=self.trip).first().delete()
        self.assertGreater(self._revision(), before)

    def test_version_changes_with_revision(self):
        with for_island(self.island):
            v1 = compute_bundle_version(self.island)
        bump_data_revision(self.island.id)
        self.island.refresh_from_db()
        with for_island(self.island):
            v2 = compute_bundle_version(self.island)
        self.assertNotEqual(v1, v2)

    def test_suppress_revision_bumps(self):
        before = self._revision()
        with suppress_revision_bumps():
            Stop.objects.create(
                island=self.island,
                name='Vila Franca',
                cleaned_name='vila franca',
                latitude=37.71,
                longitude=-25.43,
            )
        self.assertEqual(self._revision(), before)
