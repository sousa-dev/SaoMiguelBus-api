"""Safety-critical content cannot publish without human review (SDD 00 D16, 02 §5.2.3).
An AI-hallucinated tide or access warning is a physical-safety failure, not a content bug —
this is enforced at the DB level, not just in application code, deliberately."""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import TestCase

from atlas.models import AtlasCategory, AtlasPoi
from atlas.services import assign_category, publish
from tenancy.services import get_or_create_default_island


class SafetyGateTestCase(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        self.safety_category = AtlasCategory.objects.create(
            island=self.island, slug='test-natural-pools', name={'en': 'Natural pools'},
            is_safety_critical=True,
        )
        self.safe_category = AtlasCategory.objects.create(
            island=self.island, slug='test-viewpoints', name={'en': 'Viewpoints'},
            is_safety_critical=False,
        )

    def _make(self, category) -> AtlasPoi:
        poi = AtlasPoi(island=self.island, name={'en': 'Test'}, latitude=37.8, longitude=-25.5)
        assign_category(poi, category)
        poi.save()
        return poi

    def test_is_safety_critical_denormalised_from_category(self):
        poi = self._make(self.safety_category)
        self.assertTrue(poi.is_safety_critical)

        safe_poi = self._make(self.safe_category)
        self.assertFalse(safe_poi.is_safety_critical)

    def test_cannot_publish_unreviewed_safety_critical_poi(self):
        poi = self._make(self.safety_category)
        poi.is_published = True
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                poi.save()

    def test_can_publish_after_safety_review(self):
        poi = self._make(self.safety_category)
        poi.is_safety_reviewed = True
        poi.save()
        publish(poi)  # must not raise
        poi.refresh_from_db()
        self.assertTrue(poi.is_published)

    def test_non_safety_critical_publishes_freely(self):
        poi = self._make(self.safe_category)
        publish(poi)  # must not raise
        poi.refresh_from_db()
        self.assertTrue(poi.is_published)
