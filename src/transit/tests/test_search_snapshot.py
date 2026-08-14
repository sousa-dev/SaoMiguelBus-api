"""S0 baseline: freeze what ``search_routes`` returns today.

This snapshot is taken BEFORE the AzoresBus matcher rewrite and is frozen for the
rest of that project. It is the baseline every later stage diffs against, and it
is worthless if recorded after the matcher changes.

The golden file is RECORDED from actual behaviour, never hand-authored. To
re-record deliberately (which should essentially never happen after S0):

    RECORD_SEARCH_SNAPSHOT=1 pytest transit/tests/test_search_snapshot.py

This module owns the recording mechanism and validates the artifact. The
behavioural gate — "current behaviour equals the baseline except for reviewed
changes" — lives in ``test_search_diff.py`` so there is exactly one such
assertion in the suite.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from django.test import TestCase

from tenancy.services import for_island
from transit.services.search import search_routes
from transit.tests.fixtures_search import (
    QUERIES,
    ensure_search_snapshot_fixtures,
    normalize_results,
)


GOLDEN_PATH = Path(__file__).parent / 'fixtures' / 'search_snapshot_s0.json'


def collect_snapshot() -> dict[str, list[dict]]:
    """Run every snapshot query and return normalized results by query key."""
    island, trips = ensure_search_snapshot_fixtures()
    snapshot: dict[str, list[dict]] = {}
    with for_island(island):
        for key, kwargs in QUERIES:
            results = search_routes(**kwargs)
            snapshot[key] = normalize_results(results, trips)
    return snapshot


def load_golden() -> dict[str, list[dict]]:
    return json.loads(GOLDEN_PATH.read_text(encoding='utf-8'))


class SearchSnapshotArtifactTests(TestCase):
    def test_golden_exists(self):
        if os.environ.get('RECORD_SEARCH_SNAPSHOT'):
            snapshot = collect_snapshot()
            GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
            GOLDEN_PATH.write_text(
                json.dumps(snapshot, indent=2, ensure_ascii=False, sort_keys=True) + '\n',
                encoding='utf-8',
            )

        self.assertTrue(
            GOLDEN_PATH.exists(),
            f'S0 golden snapshot missing at {GOLDEN_PATH}. Record it with '
            'RECORD_SEARCH_SNAPSHOT=1 before any change to the matcher.',
        )

    def test_golden_covers_every_query(self):
        """Guards against a query silently disappearing from the baseline."""
        self.assertEqual(sorted(load_golden()), sorted(key for key, _ in QUERIES))

    def test_fixtures_build_and_all_queries_execute(self):
        snapshot = collect_snapshot()
        self.assertEqual(sorted(snapshot), sorted(key for key, _ in QUERIES))
