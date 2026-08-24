"""Emit the upstream stop payload with canonical names, for the client repos.

The webapp and Expo app both mirror `build_area_index` in TypeScript and
contract-test it against a byte-identical copy of `stops.json`. That fixture is
RAW upstream data, so once the API started storing canonical names those tests
were pinning a name domain production no longer uses -- still green, still
asserting 83 areas, while the API served 79.

This writes the derived fixture those tests should use instead. Read-only and
deterministic: same input, same bytes.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand

from azoresbus.services_names import canonicalize


FIXTURE = Path(__file__).resolve().parents[3] / 'azoresbus/tests/fixtures/stops.json'


class Command(BaseCommand):
    help = 'Write stops.json with canonical names to stdout or --out.'

    def add_arguments(self, parser):
        parser.add_argument('--out', default='', help='Destination file (default stdout).')
        parser.add_argument('--source', default=str(FIXTURE))

    def handle(self, *args, **options):
        raw = json.loads(Path(options['source']).read_text(encoding='utf-8'))
        canonical = [
            {**stop, 'name': canonicalize(stop['name'], str(stop['nameShort']))}
            for stop in raw
        ]
        payload = json.dumps(canonical, ensure_ascii=False, indent=2) + '\n'

        if options['out']:
            Path(options['out']).write_text(payload, encoding='utf-8')
            self.stdout.write(
                f"{len(canonical)} poles, "
                f"{len({s['name'] for s in canonical})} distinct names -> {options['out']}"
            )
        else:
            self.stdout.write(payload)
