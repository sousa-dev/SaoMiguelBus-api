"""02 section 7.0 acceptance: no unfiltered Trip/Stop/Line reader survives.

    "a grep for `Trip.objects`, `Stop.objects`, `Line.objects` outside
     `azoresbus/` returns no unfiltered call site, or each one carries a comment
     saying why it is dataset-agnostic."

A grep someone has to remember to run is not a guard, so it is a test. It fails
when a new dataset-blind reader is added, which is the failure mode that lets the
two networks leak into each other months after S1 shipped.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase


SRC = Path(__file__).resolve().parents[2]

# Apps that read transit rows. `azoresbus/` is exempt: it owns the import side
# and is dataset-scoped by construction.
SCANNED = ('transit', 'compat', 'atlas', 'trails', 'tenancy')

READER = re.compile(
    r'\b(Trip|Stop|Line|StopGroup|RouteInfo)\.objects\.'
    r'(all|filter|get|exclude|count|update_or_create|create)\b'
)

# Call sites that are dataset-agnostic on purpose. Each needs a reason, and the
# reason has to be defensible -- this list is the review surface.
EXEMPT = {
    # Data-quality sweep: every stop in every network should be in-radius.
    'transit/management/commands/validate_stop_coordinates.py',
}

SKIP_DIRS = ('/migrations/', '/tests/', '/__pycache__/')


def python_files():
    for app in SCANNED:
        for path in (SRC / app).rglob('*.py'):
            rel = str(path.relative_to(SRC))
            if any(part in f'/{rel}' for part in SKIP_DIRS):
                continue
            yield rel, path


def reader_call_sites():
    """Yield (relpath, lineno, source-window) for every reader call."""
    for rel, path in python_files():
        lines = path.read_text(encoding='utf-8').splitlines()
        for index, line in enumerate(lines):
            if not READER.search(line):
                continue
            # A queryset call is often split across lines; look at the whole
            # expression plus the two lines above it for an explanatory comment.
            window = '\n'.join(lines[max(0, index - 2):index + 8])
            yield rel, index + 1, window


class ReaderSweepAcceptanceTests(SimpleTestCase):
    def test_every_reader_is_filtered_or_justified(self):
        offenders = []
        for rel, lineno, window in reader_call_sites():
            if rel in EXEMPT:
                continue
            if 'dataset' in window:
                continue
            offenders.append(f'{rel}:{lineno}')

        self.assertEqual(
            offenders,
            [],
            'Dataset-blind readers found. Either filter on dataset, or add the '
            'path to EXEMPT with a comment saying why it is dataset-agnostic '
            '(02 section 7.0):\n  ' + '\n  '.join(offenders),
        )

    def test_scan_actually_finds_readers(self):
        """Guards the guard: a broken regex would make the test vacuously pass."""
        found = list(reader_call_sites())
        self.assertGreater(
            len(found), 15, f'reader scan only matched {len(found)} sites',
        )

    def test_exempt_paths_still_exist(self):
        for rel in EXEMPT:
            self.assertTrue(
                (SRC / rel).exists(),
                f'EXEMPT references a path that no longer exists: {rel}',
            )
