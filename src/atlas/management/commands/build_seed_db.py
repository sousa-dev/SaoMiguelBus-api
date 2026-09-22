"""Build atlas-seed.db — the SQLite file the Expo app bundles at build time (SDD 01 §5.3).

Guarded against the mistake that shipped once already: this was run against the local dev
sqlite database, whose per-island revision counters ran ~3-6x ahead of production's. Every
install then started life with a sync cursor from the future, `revision__gt=since` matched
nothing, and delta sync was a permanent silent no-op — the app looked fine because everything
on screen came from the seed itself.
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from atlas.models import AtlasRevision
from atlas.seed_db import build_seed_db


class Command(BaseCommand):
    help = 'Build atlas-seed.db from all published, active atlas rows across every island.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            default='media/atlas/atlas-seed.db',
            help='Output path (default: media/atlas/atlas-seed.db)',
        )
        parser.add_argument(
            '--islands',
            help=(
                'Comma-separated island keys to include, e.g. '
                'madeira,porto-santo,desertas,selvagens for the Madeira app. '
                'Default: every island (the Azores app bundle).'
            ),
        )
        parser.add_argument(
            '--without-trails',
            action='store_true',
            dest='without_trails',
            help=(
                'Leave trail rows out. Use this for any app that ships a release trail pack: '
                'the client only attaches bundled GPX to rows still at revision 0, so a '
                'seeded trail is skipped by the pack and ends up with no offline track.'
            ),
        )
        parser.add_argument(
            '--allow-non-production',
            action='store_true',
            dest='allow_non_production',
            help=(
                'Build from a non-production database anyway. For tests and local schema work '
                'only — the result must never be shipped in an app binary.'
            ),
        )

    def handle(self, *args, **options):
        self._check_database(allow_non_production=options['allow_non_production'])

        output_path = Path(options['output'])
        island_keys = None
        if options.get('islands'):
            island_keys = [key.strip() for key in options['islands'].split(',') if key.strip()]
        try:
            counts = build_seed_db(
                output_path,
                island_keys=island_keys,
                include_trails=not options.get('without_trails'),
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f'build_seed_db → {output_path}: {counts}'))

        # These are the starting sync cursors baked into every install. They must match the
        # revisions of the server the app will actually talk to — print them so a mismatch is
        # visible at build time rather than as "sync says OK but nothing appears" in the field.
        self.stdout.write('Seeded sync cursors (client starts delta sync from these):')
        revisions = AtlasRevision.objects.select_related('island').order_by('island__key')
        if island_keys is not None:
            revisions = revisions.filter(island__key__in=island_keys)
        for revision in revisions:
            self.stdout.write(f'  {revision.island.key:12} {revision.current}')

    def _check_database(self, *, allow_non_production: bool) -> None:
        vendor = connection.vendor
        name = connection.settings_dict.get('NAME')
        if vendor != 'sqlite':
            self.stdout.write(f'Building from {vendor} database {name!r}')
            return

        message = (
            f'Refusing to build atlas-seed.db from a {vendor} database ({name!r}).\n'
            'Production runs PostgreSQL, and a seed carries each island\'s revision counter '
            'forward as the client\'s starting sync cursor. Seeding from a different database '
            'ships cursors that do not match the server, which makes delta sync a permanent '
            'no-op on every install.\n'
            'Point DB_HOST/DB_NAME at production and re-run, or pass --allow-non-production '
            'if this build is not going into an app binary.'
        )
        if not allow_non_production:
            raise CommandError(message)
        self.stdout.write(self.style.WARNING(f'--allow-non-production set. {message}'))
