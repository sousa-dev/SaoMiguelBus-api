"""A full sync from revision 0 must deliver every row, whatever the revision distribution.

Real incident: each entity bucket is limited independently, but the page cursor was the max
revision across *all* buckets. Once trails were imported they occupied the top of the range
(3027-3056 on sao-miguel) while POIs sat at 51-580 truncated at the 500 limit — so the cursor
jumped to 3056 and POIs 581-3026 were never requested again. A full sync delivered 500 of 2796
POIs and reported success. It only surfaced when trails were first imported into atlas: before
that the highest revisions belonged to POIs themselves, so max() happened to be safe.
"""

from __future__ import annotations

from django.test import TestCase

from atlas.models import AtlasCategory, AtlasPoi, AtlasTrail
from atlas.services import build_sync_page, publish
from tenancy.services import get_or_create_default_island


def drain(island, *, limit: int) -> dict[str, set[str]]:
    """Page exactly as lib/atlas/sync.ts does, collecting everything delivered."""
    seen: dict[str, set[str]] = {'pois': set(), 'trails': set(), 'categories': set()}
    since = 0
    for _ in range(200):
        page = build_sync_page(island, since=since, limit=limit)
        seen['pois'].update(p['uid'] for p in page['pois'])
        seen['trails'].update(t['uid'] for t in page['trails'])
        seen['categories'].update(c['slug'] for c in page['categories'])
        if not page['has_more']:
            return seen
        assert page['revision'] > since, f'cursor stalled at {since}'
        since = page['revision']
    raise AssertionError('paging did not terminate')


class SyncPagingCompletenessTestCase(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        self.category = AtlasCategory.objects.create(
            island=self.island, slug='paging-cat', name={'en': 'Cat'}, revision=1,
        )

    def _make_pois(self, count: int) -> None:
        for index in range(count):
            poi = AtlasPoi.objects.create(
                island=self.island, category=self.category, source_ref=f'poi-{index}',
                name={'en': f'POI {index}'}, latitude=37.8, longitude=-25.5,
            )
            publish(poi)

    def _make_trails(self, count: int) -> None:
        for index in range(count):
            trail = AtlasTrail.objects.create(
                island=self.island, source=AtlasTrail.SOURCE_TRAILS, source_ref=f'trail-{index}',
                name={'en': f'Trail {index}'}, start_lat=37.8, start_lon=-25.5,
            )
            publish(trail)

    def test_trails_imported_after_pois_do_not_strand_them(self):
        """The exact production shape: many POIs, then trails imported afterwards so they hold
        the highest revisions. POIs must still all arrive."""
        self._make_pois(25)
        self._make_trails(5)  # allocated last => highest revisions

        seen = drain(self.island, limit=10)

        self.assertEqual(len(seen['pois']), 25)
        self.assertEqual(len(seen['trails']), 5)

    def test_full_drain_with_every_bucket_truncated(self):
        self._make_pois(30)
        self._make_trails(12)

        seen = drain(self.island, limit=5)

        self.assertEqual(len(seen['pois']), 30)
        self.assertEqual(len(seen['trails']), 12)
        self.assertIn('paging-cat', seen['categories'])

    def test_cursor_never_passes_an_undelivered_row(self):
        self._make_pois(25)
        self._make_trails(5)

        page = build_sync_page(self.island, since=0, limit=10)
        highest_delivered_poi = max(p['revision'] for p in page['pois'])

        # Whatever the cursor is, no POI may exist between the last one delivered and it —
        # that gap is precisely what used to be lost.
        stranded = AtlasPoi.objects.filter(
            island=self.island, is_published=True, is_active=True,
            revision__gt=highest_delivered_poi, revision__lte=page['revision'],
        )
        self.assertFalse(stranded.exists())

    def test_small_dataset_still_completes_in_one_page(self):
        self._make_pois(3)
        self._make_trails(2)

        page = build_sync_page(self.island, since=0, limit=500)

        self.assertFalse(page['has_more'])
        self.assertEqual(len(page['pois']), 3)
        self.assertEqual(len(page['trails']), 2)
        self.assertEqual(page['revision'], page['total_revision'])
