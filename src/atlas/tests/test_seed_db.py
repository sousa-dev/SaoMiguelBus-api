"""build_seed_db regression: category.slug repeats across islands (e.g. 'bus-stop' exists on
all nine), so the seed DB's category table must key on (island, slug), not slug alone — a real
bug caught manually once the seed DB went archipelago-wide (SDD 01 §5.3)."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from django.test import TestCase

from atlas.models import AtlasCategory
from atlas.seed_db import build_seed_db
from tenancy.models import Island
from tenancy.services import get_or_create_default_island


class SeedDbMultiIslandTestCase(TestCase):
    def setUp(self):
        self.island_a = get_or_create_default_island('sao-miguel')
        self.island_b, _ = Island.objects.get_or_create(
            key='test-seed-second-island',
            defaults={**Island.default_sao_miguel(), 'key': 'test-seed-second-island', 'name': 'Second'},
        )
        # island_a (sao-miguel) already carries a migration-seeded 'bus-stop' category —
        # get_or_create so this test doesn't depend on whether that seed ran.
        for island in (self.island_a, self.island_b):
            AtlasCategory.objects.get_or_create(
                island=island, slug='test-seed-shared-slug',
                defaults={'name': {'en': 'Shared slug'}, 'is_active': True},
            )

    def test_same_slug_on_two_islands_does_not_collide(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'seed.db'
            build_seed_db(output)

            conn = sqlite3.connect(output)
            rows = conn.execute(
                "SELECT island, slug FROM category WHERE slug = 'test-seed-shared-slug' ORDER BY island",
            ).fetchall()
            conn.close()
            self.assertEqual(
                rows,
                [
                    ('sao-miguel', 'test-seed-shared-slug'),
                    ('test-seed-second-island', 'test-seed-shared-slug'),
                ],
            )
