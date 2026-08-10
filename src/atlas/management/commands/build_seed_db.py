"""Build atlas-seed.db — the SQLite file the Expo app bundles at build time (SDD 01 §5.3)."""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand

from atlas.seed_db import build_seed_db


class Command(BaseCommand):
    help = 'Build atlas-seed.db from all published, active atlas rows across every island.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            default='media/atlas/atlas-seed.db',
            help='Output path (default: media/atlas/atlas-seed.db)',
        )

    def handle(self, *args, **options):
        output_path = Path(options['output'])
        counts = build_seed_db(output_path)
        self.stdout.write(self.style.SUCCESS(f'build_seed_db → {output_path}: {counts}'))
