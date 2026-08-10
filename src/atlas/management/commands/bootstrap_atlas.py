"""Idempotent atlas bootstrap — safe to run on every app start (Docker entrypoint, Procfile,
whatever precedes `runserver`/`gunicorn`). Never touches the network; every step is a local
DB or file read, so it can't fail a deploy on a flaky Overpass request or add real startup
latency.

Two jobs, run for every atlas-enabled island:

1. **Self-heal the category taxonomy.** `atlas.0003_seed_categories` seeds AtlasCategory from
   categories.json, but only for islands where `feature_flags.atlas=True` *at the time that
   migration ran* — a real bug this uncovered: on this environment, `tenancy.0018` (which
   turns atlas on for São Miguel) has no dependency ordering relative to `atlas.0003`, so
   São Miguel's migration ran with zero categories seeded. Re-running the same
   `update_or_create` here on every boot is a no-op once categories exist, and self-heals any
   island that's missing them for the same reason.

2. **Seed each island's initial catalogue, once.** If an island has zero AtlasPoi rows, run
   every registered importer for it (curated/transit/minibus/trails/osm — each one already
   no-ops gracefully if its own source has nothing to import, per BaseImporter). "Zero rows"
   is the literal gate for "hasn't run before" — no separate flag table needed, and it
   self-heals if someone truncates the table in a dev environment.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from atlas.importers import IMPORTER_REGISTRY
from atlas.models import AtlasCategory, AtlasPoi, AtlasRevision
from tenancy.models import Island


class Command(BaseCommand):
    help = 'Idempotent atlas startup bootstrap: backfill categories, seed first-run catalogue data.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--island', help='Only bootstrap this island key (default: every atlas-enabled island).',
        )

    def handle(self, *args, **options):
        categories = self._load_categories()
        islands = Island.objects.filter(feature_flags__atlas=True).order_by('key')
        if options.get('island'):
            islands = islands.filter(key=options['island'])
            if not islands.exists():
                raise CommandError(f'No atlas-enabled island with key={options["island"]!r}')

        for island in islands:
            created_categories = self._ensure_categories(island, categories)
            AtlasRevision.objects.get_or_create(island=island)

            if created_categories:
                self.stdout.write(f'{island.key}: backfilled {created_categories} missing categories')

            revisioned = self._ensure_category_revisions(island)
            if revisioned:
                self.stdout.write(f'{island.key}: assigned sync revisions to {revisioned} categories')

            if AtlasPoi.objects.filter(island=island).exists():
                continue

            self.stdout.write(f'{island.key}: no POIs yet — running first-time import')
            for source, importer_cls in IMPORTER_REGISTRY.items():
                try:
                    result = importer_cls(island).run()
                except Exception as exc:  # noqa: BLE001 — one importer's failure must not block the rest
                    self.stderr.write(self.style.ERROR(f'{island.key}: {source} importer failed: {exc}'))
                    continue
                self.stdout.write(f'{island.key}: {source} → {result}')

        self.stdout.write(self.style.SUCCESS('atlas bootstrap complete'))

    def _load_categories(self) -> list[dict]:
        path = Path(__file__).resolve().parent.parent.parent / 'data' / 'categories.json'
        with path.open(encoding='utf-8') as handle:
            return json.load(handle)

    def _ensure_category_revisions(self, island: Island) -> int:
        """Give every revision-0 category a real revision so delta sync can actually send it.

        Real bug this fixes: `atlas.0003_seed_categories` (and _ensure_categories above) create
        AtlasCategory rows without touching `revision`, so they keep the model default of 0.
        `build_sync_page` filters `revision__gt=since`, and `since` starts at 0 — so a
        revision-0 category matches no page, ever. Categories reached clients only via the
        bundled seed DB, meaning any later rename/recolour/new category silently never
        propagated to an installed app. Idempotent: once a row has a non-zero revision this is
        a no-op, so it costs one revision bump per category, once.
        """
        stale = AtlasCategory.objects.filter(island=island, revision=0)
        count = 0
        for category in stale:
            category.revision = AtlasRevision.next_for(island)
            category.save(update_fields=['revision'])
            count += 1
        return count

    def _ensure_categories(self, island: Island, categories: list[dict]) -> int:
        existing_slugs = set(AtlasCategory.objects.filter(island=island).values_list('slug', flat=True))
        missing = [row for row in categories if row['slug'] not in existing_slugs]
        for row in missing:
            AtlasCategory.objects.update_or_create(
                island=island,
                slug=row['slug'],
                defaults={
                    'name': row['name'],
                    'group': row['group'],
                    'icon': row['icon'],
                    'color': row['color'],
                    'sort_order': row['sort_order'],
                    'is_safety_critical': row['is_safety_critical'],
                    'is_active': True,
                },
            )
        return len(missing)
