"""Normalize marketplace provider phone and WhatsApp numbers to +351XXXXXXXXX."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from marketplace import services
from tenancy.models import Island


class Command(BaseCommand):
    help = 'Fix wrongly formatted provider phone and WhatsApp numbers (+351XXXXXXXXX).'

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            '--island',
            dest='island_key',
            default='',
            help='Limit to one island key (e.g. sao-miguel). Default: all islands.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report changes without writing to the database.',
        )

    def handle(self, *args, **options) -> None:
        island_key = (options.get('island_key') or '').strip()
        dry_run = bool(options.get('dry_run'))
        island = None
        if island_key:
            try:
                island = Island.objects.get(key=island_key)
            except Island.DoesNotExist as exc:
                raise SystemExit(f'Unknown island key: {island_key}') from exc

        result = services.fix_provider_phone_numbers(island=island, dry_run=dry_run)
        mode = 'DRY RUN' if dry_run else 'APPLIED'
        self.stdout.write(
            f'[{mode}] scanned={result["scanned"]} updated={result["updated"]} '
            f'unchanged={result["unchanged"]} skipped_fields={result["skipped_fields"]}'
        )
        for change in result['changes']:
            parts = [f'#{change["id"]} {change["name"]} ({change["island"]})']
            for field in ('phone', 'whatsapp'):
                if field in change:
                    parts.append(f'{field}: {change[field]["from"]!r} -> {change[field]["to"]!r}')
            self.stdout.write('  ' + ' | '.join(parts))
