"""Import Mini Bus PDF/SVG assets into MEDIA_ROOT."""

from __future__ import annotations

import hashlib
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from minibus.models import MinibusDocument
from minibus.services import default_source_dir, load_catalog, mark_imported, seed_catalog
from tenancy.services import for_island, get_or_create_default_island


def file_revision(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()[:16]


class Command(BaseCommand):
    help = 'Import Mini Bus PDF/SVG files and attach them to document rows.'

    def add_arguments(self, parser):
        parser.add_argument('--island', default='sao-miguel', help='Island key (default: sao-miguel)')
        parser.add_argument(
            '--source-dir',
            default='',
            help='Directory with source PDFs/SVG (default: minibus/data/source or MINIBUS_SOURCE_DIR)',
        )
        parser.add_argument(
            '--skip-seed',
            action='store_true',
            help='Skip JSON catalog upsert (only copy files)',
        )

    def handle(self, *args, **options):
        island_key = options['island']
        island = get_or_create_default_island(island_key)

        source_dir = Path(options['source_dir']) if options['source_dir'] else default_source_dir()
        if not source_dir.is_dir():
            raise CommandError(f'Source directory not found: {source_dir}')

        with for_island(island):
            if not options['skip_seed']:
                counts = seed_catalog(island)
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Seeded catalog: {counts["lines"]} lines, '
                        f'{counts["tariffs"]} tariffs, {counts["documents"]} documents',
                    ),
                )

            catalog = load_catalog()
            revisions: list[str] = []
            copied = 0

            for row in catalog['documents']:
                source_path = source_dir / row['source_filename']
                if not source_path.is_file():
                    raise CommandError(f'Missing source file: {source_path}')

                document = MinibusDocument.objects.filter(island=island, slug=row['slug']).first()
                if document is None:
                    raise CommandError(f'Document row missing for slug {row["slug"]} — run migrations first')

                revisions.append(file_revision(source_path))
                with source_path.open('rb') as handle:
                    content = handle.read()

                filename = f'{row["slug"]}{source_path.suffix.lower()}'
                if document.file and document.file.name:
                    document.file.delete(save=False)
                document.file.save(filename, ContentFile(content), save=True)
                copied += 1

            mark_imported(island, source_revision='-'.join(sorted(set(revisions))[:4]))

        self.stdout.write(
            self.style.SUCCESS(
                f'Imported {copied} files into {settings.MEDIA_ROOT}/minibus/ for {island_key}',
            ),
        )
