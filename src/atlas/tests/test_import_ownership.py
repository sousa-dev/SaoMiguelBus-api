"""Import-ownership rule (SDD 02 §5.2.1, HANDOVER item 4): each importer may only write rows
carrying its own `source`. Covers the DB constraint and the upsert scoping that makes it
structurally impossible for one importer's run to touch another's rows."""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import TestCase

from atlas.importers.base import BaseImporter, ImportRow
from atlas.models import AtlasCategory, AtlasPoi
from tenancy.services import get_or_create_default_island


class _FakeOsmImporter(BaseImporter):
    SOURCE = AtlasPoi.SOURCE_OSM

    def __init__(self, island, rows):
        super().__init__(island)
        self._rows = rows

    def rows(self):
        return iter(self._rows)


class _FakeCuratedImporter(BaseImporter):
    SOURCE = AtlasPoi.SOURCE_CURATED

    def __init__(self, island, rows):
        super().__init__(island)
        self._rows = rows

    def rows(self):
        return iter(self._rows)


class ImportOwnershipTestCase(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        self.category = AtlasCategory.objects.create(
            island=self.island, slug='test-viewpoints', name={'en': 'Viewpoints'},
        )

    def test_curated_tier_requires_curated_source(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AtlasPoi.objects.create(
                    island=self.island, category=self.category,
                    tier=AtlasPoi.TIER_CURATED, source=AtlasPoi.SOURCE_OSM,
                    name={'en': 'Should fail'}, latitude=37.8, longitude=-25.5,
                )

    def test_colliding_ref_across_sources_creates_separate_rows(self):
        """Same `ref`, different `source` — must never collapse into one row. This is what
        would make the monthly OSM run revert curated content sharing a coincidental id."""
        curated_row = ImportRow(
            ref='shared-ref-1', name={'en': 'Contested place'},
            latitude=37.8, longitude=-25.5, category_slug='test-viewpoints',
            tier=AtlasPoi.TIER_CURATED,
        )
        osm_row = ImportRow(
            ref='shared-ref-1', name={'en': 'Contested place'},
            latitude=37.8, longitude=-25.5, category_slug='test-viewpoints',
        )
        _FakeCuratedImporter(self.island, [curated_row]).run()
        _FakeOsmImporter(self.island, [osm_row]).run()

        self.assertEqual(
            AtlasPoi.objects.filter(island=self.island, source_ref='shared-ref-1').count(), 2,
        )
        curated = AtlasPoi.objects.get(source=AtlasPoi.SOURCE_CURATED, source_ref='shared-ref-1')
        osm = AtlasPoi.objects.get(source=AtlasPoi.SOURCE_OSM, source_ref='shared-ref-1')
        self.assertEqual(curated.tier, AtlasPoi.TIER_CURATED)
        self.assertEqual(osm.tier, AtlasPoi.TIER_STANDARD)

    def test_vanished_row_tombstoning_is_scoped_to_owning_source(self):
        """An importer's cleanup pass must only ever retire its own rows."""
        row_a = ImportRow(
            ref='osm-a', name={'en': 'OSM place A'},
            latitude=37.8, longitude=-25.5, category_slug='test-viewpoints',
        )
        row_b = ImportRow(
            ref='osm-b', name={'en': 'OSM place B'},
            latitude=37.9, longitude=-25.6, category_slug='test-viewpoints',
        )
        curated_row = ImportRow(
            ref='curated-a', name={'en': 'Curated place'},
            latitude=38.0, longitude=-25.7, category_slug='test-viewpoints',
        )

        _FakeOsmImporter(self.island, [row_a, row_b]).run()
        _FakeCuratedImporter(self.island, [curated_row]).run()

        # Re-run OSM without row_b — it vanished upstream.
        _FakeOsmImporter(self.island, [row_a]).run()

        vanished = AtlasPoi.objects.get(source=AtlasPoi.SOURCE_OSM, source_ref='osm-b')
        self.assertFalse(vanished.is_active)
        self.assertFalse(vanished.is_published)

        # The curated row (different source) must be untouched by the OSM importer's cleanup.
        curated = AtlasPoi.objects.get(source=AtlasPoi.SOURCE_CURATED, source_ref='curated-a')
        self.assertTrue(curated.is_active)

        still_here = AtlasPoi.objects.get(source=AtlasPoi.SOURCE_OSM, source_ref='osm-a')
        self.assertTrue(still_here.is_active)
