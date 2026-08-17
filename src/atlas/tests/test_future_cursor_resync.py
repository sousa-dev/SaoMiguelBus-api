"""A sync cursor ahead of the server must force a full resync.

Real incident this encodes: atlas-seed.db was built from a dev database whose per-island
revision counters ran ~3-6x ahead of production (sao-miguel 7944 vs 2996, pico 3803 vs 607).
Every install therefore began delta sync with `since` above the server's own counter, so
`revision__gt=since` matched nothing on every request. Sync reported success, applied zero
rows, and never self-corrected — the app looked healthy because everything on screen came
from the bundled seed. Newly published content simply never arrived.
"""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from atlas.models import AtlasCategory, AtlasPoi, AtlasRevision
from atlas.services import build_sync_page, current_revision, needs_full_resync, publish
from tenancy.services import get_or_create_default_island


class FutureCursorResyncTestCase(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        self.category = AtlasCategory.objects.create(
            island=self.island, slug='future-cursor-cat', name={'en': 'Test'}, revision=1,
        )
        self.poi = AtlasPoi.objects.create(
            island=self.island, category=self.category, source_ref='ref-1',
            name={'en': 'POI'}, latitude=37.8, longitude=-25.5,
        )
        publish(self.poi)
        self.current = current_revision(self.island)

    def test_cursor_ahead_of_server_needs_resync(self):
        self.assertTrue(needs_full_resync(self.island, self.current + 1))
        self.assertTrue(needs_full_resync(self.island, self.current + 5000))

    def test_cursor_at_or_behind_server_does_not(self):
        self.assertFalse(needs_full_resync(self.island, self.current))
        self.assertFalse(needs_full_resync(self.island, max(self.current - 1, 1)))
        self.assertFalse(needs_full_resync(self.island, 0))

    def test_page_flags_resync_and_starves_without_it(self):
        """The exact field symptom: a future cursor yields an empty page. Without the
        full_resync flag the client has no way to learn it must start over."""
        page = build_sync_page(self.island, since=self.current + 3000, limit=500)

        self.assertTrue(page['full_resync'])
        self.assertEqual(page['counts']['pois'], 0)
        self.assertEqual(page['counts']['categories'], 0)
        self.assertFalse(page['has_more'])

    def test_resync_from_zero_returns_the_data(self):
        # What the client does after honouring full_resync: wipe, restart at 0, get everything.
        page = build_sync_page(self.island, since=0, limit=500)
        self.assertEqual(page['counts']['pois'], 1)
        self.assertFalse(page['full_resync'])

    def test_island_with_no_revision_row_treats_any_cursor_as_future(self):
        AtlasRevision.objects.filter(island=self.island).delete()
        self.assertEqual(current_revision(self.island), 0)
        self.assertTrue(needs_full_resync(self.island, 1))

    def test_sync_endpoint_reports_full_resync(self):
        client = APIClient()
        response = client.get(
            '/api/v3/atlas/sync',
            {'since': self.current + 3000},
            HTTP_X_ISLAND=self.island.key,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['full_resync'])
