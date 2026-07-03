"""Tests for the ad performance reporting endpoint."""

from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from tenancy.services import get_or_create_default_island
from transit.models import Ad, AdEvent

AUTH = 'test-reporting-key'


@override_settings(AUTH_KEY=AUTH)
class AdsReportTests(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        self.now = timezone.now()
        self.ad_a = self._make_ad('Cafe Central', seen=100, clicked=10)
        self.ad_b = self._make_ad('Hotel Azul', seen=50, clicked=1)

        # Ad A: 8 impressions / 2 clicks today, 4 impressions yesterday.
        self._events(self.ad_a, AdEvent.KIND_IMPRESSION, 8, self.now, platform='android')
        self._events(self.ad_a, AdEvent.KIND_CLICK, 2, self.now, platform='android')
        self._events(self.ad_a, AdEvent.KIND_IMPRESSION, 4, self.now - timedelta(days=1))
        # Ad B: 2 impressions today on web.
        self._events(self.ad_b, AdEvent.KIND_IMPRESSION, 2, self.now, platform='web')

    def _make_ad(self, entity, *, seen=0, clicked=0):
        return Ad.objects.create(
            island=self.island,
            entity=entity,
            media='https://example.com/banner.png',
            start=self.now - timedelta(days=30),
            end=self.now + timedelta(days=30),
            advertise_on='home',
            platform='all',
            status='active',
            seen=seen,
            clicked=clicked,
        )

    def _events(self, ad, kind, count, occurred_at, platform=''):
        for _ in range(count):
            AdEvent.objects.create(
                island=self.island, ad=ad, kind=kind,
                platform=platform, occurred_at=occurred_at,
            )

    def _get(self, **params):
        params.setdefault('key', AUTH)
        return self.client.get(
            '/api/v3/analytics/reports/ads/overview', params, HTTP_X_ISLAND=self.island.key
        )

    def test_totals_and_ctr(self):
        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['totals']['impressions'], 14)
        self.assertEqual(data['totals']['clicks'], 2)
        self.assertAlmostEqual(data['totals']['ctr'], round(2 / 14, 4))

    def test_series_buckets_split_impressions_and_clicks(self):
        data = self._get().json()
        self.assertTrue(data['series'])
        total_impressions = sum(row['impressions'] for row in data['series'])
        total_clicks = sum(row['clicks'] for row in data['series'])
        self.assertEqual(total_impressions, 14)
        self.assertEqual(total_clicks, 2)
        for row in data['series']:
            if row['impressions']:
                self.assertAlmostEqual(row['ctr'], round(row['clicks'] / row['impressions'], 4))

    def test_per_ad_table_range_and_lifetime(self):
        data = self._get().json()
        by_entity = {row['entity']: row for row in data['ads']}
        cafe = by_entity['Cafe Central']
        self.assertEqual(cafe['impressions'], 12)
        self.assertEqual(cafe['clicks'], 2)
        self.assertEqual(cafe['lifetime_seen'], 100)
        self.assertEqual(cafe['lifetime_clicked'], 10)
        hotel = by_entity['Hotel Azul']
        self.assertEqual(hotel['impressions'], 2)
        self.assertEqual(hotel['ctr'], 0.0)

    def test_ad_id_filter(self):
        data = self._get(ad_id=self.ad_b.id).json()
        self.assertEqual(data['totals']['impressions'], 2)
        self.assertEqual(len(data['ads']), 1)
        self.assertEqual(data['ads'][0]['entity'], 'Hotel Azul')

    def test_platform_filter(self):
        data = self._get(platform='web').json()
        self.assertEqual(data['totals']['impressions'], 2)
        self.assertEqual(data['totals']['clicks'], 0)

    def test_compare_block(self):
        # Current window = today only → previous window = yesterday (4 impressions).
        start = self.now.date().isoformat()
        end = self.now.date().isoformat()
        data = self._get(start=start, end=end, compare=1).json()
        self.assertIn('previous', data)
        self.assertEqual(data['previous']['totals']['impressions'], 4)

    def test_first_event_present(self):
        data = self._get().json()
        self.assertIsNotNone(data['first_event'])

    def test_requires_auth(self):
        resp = self.client.get(
            '/api/v3/analytics/reports/ads/overview', HTTP_X_ISLAND=self.island.key
        )
        self.assertEqual(resp.status_code, 401)
