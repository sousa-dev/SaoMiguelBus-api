"""Run one atlas importer for one island. Re-runnable and idempotent."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from atlas.importers import IMPORTER_REGISTRY
from tenancy.models import Island


class Command(BaseCommand):
    help = 'Import atlas content from one source into one island (e.g. --source osm --island sao-miguel).'

    def add_arguments(self, parser):
        parser.add_argument('--source', required=True, choices=sorted(IMPORTER_REGISTRY))
        parser.add_argument('--island', required=True, help='Island key, e.g. sao-miguel')

    def handle(self, *args, **options):
        island = Island.objects.filter(key=options['island']).first()
        if island is None:
            raise CommandError(f'Island not found: {options["island"]}')

        importer_cls = IMPORTER_REGISTRY[options['source']]
        importer = importer_cls(island)
        result = importer.run()

        self.stdout.write(
            self.style.SUCCESS(f'import_atlas source={options["source"]} island={island.key}: {result}'),
        )
