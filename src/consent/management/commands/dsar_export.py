"""DSAR export management command (stub)."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from consent.dsar import dsar_export_bundle, resolve_session_hash


class Command(BaseCommand):
    help = 'Export DSAR bundle for a session (stub — extend as modules ship).'

    def add_arguments(self, parser):
        parser.add_argument('--session-id', type=str, default='')
        parser.add_argument('--session-hash', type=str, default='')
        parser.add_argument('--island', type=str, default='sao-miguel')

    def handle(self, *args, **options):
        session_hash = resolve_session_hash(
            session_id=options['session_id'] or None,
            session_hash=options['session_hash'] or None,
            island_key=options['island'],
        )
        if not session_hash:
            raise CommandError('Provide --session-id or --session-hash')

        bundle = dsar_export_bundle(session_hash=session_hash)
        self.stdout.write(json.dumps(bundle, indent=2, default=str))
