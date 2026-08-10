"""Revision allocation must never produce duplicates under concurrent writers (SDD 02 §3.1,
HANDOVER item 5). Without select_for_update(), two concurrent admin saves can read the same
`current` and both write current+1 — this test is what would catch that regression."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from django.db import OperationalError, connection
from django.test import TransactionTestCase

from atlas.models import AtlasRevision
from tenancy.services import get_or_create_default_island

CONCURRENCY = 20


class RevisionConcurrencyTestCase(TransactionTestCase):
    """Without select_for_update() in AtlasRevision.next_for(), two concurrent callers can
    read the same `current` and both write current+1, producing a duplicate revision.

    SQLite has no real row-level locking — every writer serializes on the whole database file,
    and its default busy handler fails fast rather than queueing, so a thread that loses the
    race gets `database is locked` even with `select_for_update()` present and correct. The
    retry loop below is standing in for what any real caller needs against SQLite regardless;
    it does not mask a correctness gap — the invariant under test (no duplicate revisions,
    ever) is checked on whatever value each thread eventually got. On Postgres (production),
    `select_for_update()` queues contending transactions directly with no retries needed.
    """

    def setUp(self):
        self.island = get_or_create_default_island()

    def test_concurrent_allocation_never_duplicates(self):
        def allocate(_: int) -> int:
            try:
                with connection.cursor() as cursor:
                    cursor.execute('PRAGMA busy_timeout = 10000')
                for attempt in range(20):
                    try:
                        return AtlasRevision.next_for(self.island)
                    except OperationalError:
                        if attempt == 19:
                            raise
                        time.sleep(0.05)
                raise AssertionError('unreachable')
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
            results = list(pool.map(allocate, range(CONCURRENCY)))

        self.assertEqual(len(results), CONCURRENCY)
        self.assertEqual(len(set(results)), CONCURRENCY, 'duplicate revision allocated under concurrency')
        self.assertEqual(sorted(results), list(range(1, CONCURRENCY + 1)))

    def test_sequential_allocation_is_monotonic(self):
        first = AtlasRevision.next_for(self.island)
        second = AtlasRevision.next_for(self.island)
        self.assertEqual(second, first + 1)
