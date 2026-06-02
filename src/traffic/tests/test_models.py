"""U1 model-level tests: defaults, ownership, uniqueness, lifecycle status."""

from __future__ import annotations

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from tenancy.services import get_or_create_default_island
from traffic.models import TrafficCategory, TrafficConfirmation, TrafficReport


class TrafficModelTests(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        self.category = TrafficCategory.objects.create(
            island=self.island, name='Acidente', slug='acidente', default_ttl_minutes=120
        )

    def _report(self, **kwargs):
        defaults = dict(
            island=self.island,
            category=self.category,
            created_by_session_hash='sess-a',
            latitude=37.74,
            longitude=-25.66,
            expires_at=timezone.now() + timedelta(minutes=120),
        )
        defaults.update(kwargs)
        return TrafficReport.objects.create(**defaults)

    def test_report_defaults_active(self):
        report = self._report()
        self.assertEqual(report.status, TrafficReport.ACTIVE)
        self.assertEqual(report.confirm_count, 0)
        self.assertEqual(report.deny_count, 0)

    def test_is_owned_by(self):
        report = self._report(created_by_session_hash='owner-hash')
        self.assertTrue(report.is_owned_by('owner-hash'))
        self.assertFalse(report.is_owned_by('other-hash'))
        self.assertFalse(report.is_owned_by(''))

    def test_category_unique_per_island(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TrafficCategory.objects.create(
                    island=self.island, name='Acidente 2', slug='acidente'
                )

    def test_confirmation_unique_per_session_per_report(self):
        report = self._report()
        TrafficConfirmation.objects.create(
            island=self.island, report=report, session_hash='sess-x',
            vote=TrafficConfirmation.STILL_THERE,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TrafficConfirmation.objects.create(
                    island=self.island, report=report, session_hash='sess-x',
                    vote=TrafficConfirmation.GONE,
                )

    def test_active_filter_excludes_non_active(self):
        self._report(status=TrafficReport.EXPIRED)
        self._report(status=TrafficReport.ACTIVE, created_by_session_hash='sess-b', road='EN1-1A')
        active = TrafficReport.objects.for_island(self.island).filter(
            status=TrafficReport.ACTIVE
        )
        self.assertEqual([r.road for r in active], ['EN1-1A'])
