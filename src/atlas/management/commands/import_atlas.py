"""Run one atlas importer for one island, or for every atlas-enabled island.

Re-runnable and idempotent: importers upsert on (island, source, source_ref) and tombstone
whatever vanished, so re-running only ever reconciles.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from atlas.importers import IMPORTER_REGISTRY
from tenancy.models import Island


class Command(BaseCommand):
    help = (
        'Import atlas content from one source into one island (--source osm --island sao-miguel) '
        'or into every atlas-enabled island (--source trails --all-islands).'
    )

    def add_arguments(self, parser):
        parser.add_argument('--source', required=True, choices=sorted(IMPORTER_REGISTRY))
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument('--island', help='Island key, e.g. sao-miguel')
        group.add_argument(
            '--all-islands',
            action='store_true',
            dest='all_islands',
            help='Every island with feature_flags.atlas enabled.',
        )

    def handle(self, *args, **options):
        source = options['source']
        importer_cls = IMPORTER_REGISTRY[source]

        if options.get('all_islands'):
            islands = list(Island.objects.filter(feature_flags__atlas=True).order_by('key'))
            if not islands:
                raise CommandError('No atlas-enabled islands found')
        else:
            island = Island.objects.filter(key=options['island']).first()
            if island is None:
                raise CommandError(f'Island not found: {options["island"]}')
            islands = [island]

        failed = 0
        for island in islands:
            try:
                result = importer_cls(island).run()
            except Exception as exc:  # noqa: BLE001 — one island must not block the rest
                # Matches bootstrap_atlas: this runs on every deploy, so a single bad island
                # can't be allowed to abort the reconcile for the other eight.
                failed += 1
                self.stderr.write(
                    self.style.ERROR(f'import_atlas source={source} island={island.key} failed: {exc}'),
                )
                continue
            self.stdout.write(f'import_atlas source={source} island={island.key}: {result}')

        style = self.style.WARNING if failed else self.style.SUCCESS
        self.stdout.write(
            style(f'import_atlas source={source}: {len(islands) - failed}/{len(islands)} islands ok'),
        )
