"""bootstrap_atlas regression: the idempotent startup command wired into runserver.sh.

Covers the real bug it exists to self-heal (an atlas-enabled island with zero categories,
because `atlas.0003_seed_categories` ran before that island had `feature_flags.atlas=True`)
and the "only seed once" contract the whole command is built around.
"""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from atlas.models import AtlasCategory, AtlasPoi, AtlasRevision
from tenancy.models import Island


class BootstrapAtlasTestCase(TestCase):
    def setUp(self):
        self.island, _ = Island.objects.get_or_create(
            key='test-bootstrap-island',
            defaults={**Island.default_sao_miguel(), 'key': 'test-bootstrap-island', 'name': 'Bootstrap Test'},
        )
        self.island.feature_flags = {**self.island.feature_flags, 'atlas': True}
        self.island.save(update_fields=['feature_flags'])

    def test_backfills_missing_categories(self):
        self.assertEqual(AtlasCategory.objects.filter(island=self.island).count(), 0)

        call_command('bootstrap_atlas', island=self.island.key, stdout=StringIO())

        self.assertGreater(AtlasCategory.objects.filter(island=self.island).count(), 0)

    def test_does_not_duplicate_categories_on_existing_island(self):
        call_command('bootstrap_atlas', island=self.island.key, stdout=StringIO())
        first_count = AtlasCategory.objects.filter(island=self.island).count()

        call_command('bootstrap_atlas', island=self.island.key, stdout=StringIO())
        second_count = AtlasCategory.objects.filter(island=self.island).count()

        self.assertEqual(first_count, second_count)

    def test_creates_revision_row(self):
        self.assertFalse(AtlasRevision.objects.filter(island=self.island).exists())

        call_command('bootstrap_atlas', island=self.island.key, stdout=StringIO())

        self.assertTrue(AtlasRevision.objects.filter(island=self.island).exists())

    def test_skips_import_when_island_already_has_pois(self):
        """The literal "hasn't run before" gate: a non-empty AtlasPoi table for an island means
        skip re-importing it, even though nothing here stops categories from still being
        backfilled."""
        call_command('bootstrap_atlas', island=self.island.key, stdout=StringIO())
        category = AtlasCategory.objects.filter(island=self.island).first()
        AtlasPoi.objects.create(
            island=self.island,
            category=category,
            source=AtlasPoi.SOURCE_CURATED,
            source_ref='test-existing-poi',
            name={'en': 'Existing POI'},
            latitude=37.0,
            longitude=-25.0,
            tier=AtlasPoi.TIER_CURATED,
            is_active=True,
            is_published=True,
        )
        poi_count_before = AtlasPoi.objects.filter(island=self.island).count()

        call_command('bootstrap_atlas', island=self.island.key, stdout=StringIO())

        self.assertEqual(AtlasPoi.objects.filter(island=self.island).count(), poi_count_before)

    def test_ignores_islands_without_atlas_enabled(self):
        other_island, _ = Island.objects.get_or_create(
            key='test-bootstrap-no-atlas',
            defaults={**Island.default_sao_miguel(), 'key': 'test-bootstrap-no-atlas', 'name': 'No Atlas'},
        )
        other_island.feature_flags = {**other_island.feature_flags, 'atlas': False}
        other_island.save(update_fields=['feature_flags'])

        call_command('bootstrap_atlas', island=self.island.key, stdout=StringIO())

        self.assertEqual(AtlasCategory.objects.filter(island=other_island).count(), 0)
