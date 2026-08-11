"""Delta-sync contract (SDD 02 §4): paging, tombstone visibility, tenant isolation."""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from atlas.models import AtlasCategory, AtlasPoi
from atlas.services import build_sync_page, publish, unpublish
from tenancy.services import get_or_create_default_island


def _make_poi(island, category, *, ref: str, published: bool = True) -> AtlasPoi:
    poi = AtlasPoi.objects.create(
        island=island, category=category, source_ref=ref,
        name={'en': f'POI {ref}'}, latitude=37.8, longitude=-25.5,
    )
    if published:
        publish(poi)
    return poi


class SyncPagingTestCase(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        self.category = AtlasCategory.objects.create(
            island=self.island, slug='test-sync-cat', name={'en': 'Test'}, revision=1,
        )

    def test_only_published_active_pois_appear(self):
        _make_poi(self.island, self.category, ref='published', published=True)
        _make_poi(self.island, self.category, ref='unpublished', published=False)

        page = build_sync_page(self.island, since=0, limit=500)
        refs = {p['uid'] for p in page['pois']}
        self.assertEqual(len(page['pois']), 1)
        self.assertNotIn('unpublished', [poi.source_ref for poi in AtlasPoi.objects.filter(uid__in=refs)])

    def test_unpublish_creates_visible_tombstone(self):
        poi = _make_poi(self.island, self.category, ref='to-remove', published=True)
        before = build_sync_page(self.island, since=0, limit=500)
        cursor = before['revision']

        unpublish(poi)

        page = build_sync_page(self.island, since=cursor, limit=500)
        self.assertEqual(len(page['deleted']), 1)
        self.assertEqual(page['deleted'][0]['uid'], str(poi.uid))
        self.assertEqual(page['deleted'][0]['entityType'], 'poi')
        self.assertEqual(len(page['pois']), 0)

    def test_paging_has_more_flag(self):
        for i in range(5):
            _make_poi(self.island, self.category, ref=f'page-{i}', published=True)

        page = build_sync_page(self.island, since=0, limit=2)
        self.assertEqual(len(page['pois']), 2)
        self.assertTrue(page['has_more'])

        last_page = build_sync_page(self.island, since=999999, limit=2)
        self.assertFalse(last_page['has_more'])

    def test_revision_cursor_only_returns_changes_since(self):
        _make_poi(self.island, self.category, ref='old', published=True)
        first_page = build_sync_page(self.island, since=0, limit=500)
        cursor = first_page['revision']

        _make_poi(self.island, self.category, ref='new', published=True)
        incremental = build_sync_page(self.island, since=cursor, limit=500)

        self.assertEqual(len(incremental['pois']), 1)
        self.assertEqual(incremental['pois'][0]['name']['en'], 'POI new')


class SyncApiTenantIsolationTestCase(TestCase):
    def setUp(self):
        from tenancy.models import Island

        self.island_a = get_or_create_default_island('sao-miguel')
        self.island_b, _ = Island.objects.get_or_create(
            key='test-second-island',
            defaults={**Island.default_sao_miguel(), 'key': 'test-second-island', 'name': 'Second Island'},
        )
        self.island_b.feature_flags = {**self.island_b.feature_flags, 'atlas': True}
        self.island_b.save(update_fields=['feature_flags'])

        self.cat_a = AtlasCategory.objects.create(island=self.island_a, slug='iso-cat', name={'en': 'Cat'})
        self.cat_b = AtlasCategory.objects.create(island=self.island_b, slug='iso-cat', name={'en': 'Cat'})

        _make_poi(self.island_a, self.cat_a, ref='only-in-a', published=True)
        _make_poi(self.island_b, self.cat_b, ref='only-in-b', published=True)

    def test_sync_endpoint_scopes_to_requested_island(self):
        client = APIClient()
        response = client.get('/api/v3/atlas/sync', HTTP_X_ISLAND='sao-miguel')
        self.assertEqual(response.status_code, 200)
        names = [poi['name']['en'] for poi in response.json()['pois']]
        self.assertIn('POI only-in-a', names)
        self.assertNotIn('POI only-in-b', names)

    def test_other_island_does_not_see_first_islands_rows(self):
        client = APIClient()
        response = client.get('/api/v3/atlas/sync', HTTP_X_ISLAND='test-second-island')
        self.assertEqual(response.status_code, 200)
        names = [poi['name']['en'] for poi in response.json()['pois']]
        self.assertIn('POI only-in-b', names)
        self.assertNotIn('POI only-in-a', names)


class AtlasStatsApiTestCase(TestCase):
    def setUp(self):
        from tenancy.models import Island

        self.island = get_or_create_default_island()
        self.island_b, _ = Island.objects.get_or_create(
            key='test-stats-island',
            defaults={**Island.default_sao_miguel(), 'key': 'test-stats-island', 'name': 'Stats Island'},
        )
        self.island_b.feature_flags = {**self.island_b.feature_flags, 'atlas': True}
        self.island_b.save(update_fields=['feature_flags'])

        self.category = AtlasCategory.objects.create(
            island=self.island, slug='stats-cat', name={'en': 'Stats'}, revision=1,
        )
        self.category_b = AtlasCategory.objects.create(
            island=self.island_b, slug='stats-cat', name={'en': 'Stats'}, revision=1,
        )
        _make_poi(self.island, self.category, ref='stats-1', published=True)
        _make_poi(self.island, self.category, ref='stats-2', published=True)
        _make_poi(self.island, self.category, ref='stats-hidden', published=False)
        _make_poi(self.island_b, self.category_b, ref='stats-other', published=True)

    def test_stats_endpoint_defaults_to_archipelago_totals(self):
        client = APIClient()
        # No X-Island — TenantMiddleware still binds DEFAULT_ISLAND_KEY.
        response = client.get('/api/v3/atlas/stats')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertGreaterEqual(body['pois'], 3)
        self.assertGreaterEqual(body['islands'], 2)
        self.assertIn('trails', body)
        self.assertIn('categories', body)

    def test_stats_endpoint_can_scope_to_island(self):
        client = APIClient()
        response = client.get('/api/v3/atlas/stats', HTTP_X_ISLAND='sao-miguel')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['pois'], 2)
        self.assertEqual(body['islands'], 1)
