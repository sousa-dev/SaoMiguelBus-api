"""Tests for the read-side analytics reporting API."""

from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from analytics.models import AnalyticsEvent, Stat
from tenancy.services import get_or_create_default_island

AUTH = 'test-reporting-key'


@override_settings(AUTH_KEY=AUTH)
class ReportingApiTests(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        now = timezone.now()

        for i in range(5):
            AnalyticsEvent.objects.create(
                island=self.island,
                module='transit',
                event_type='search',
                properties={'origin': 'PDL'},
                session_hash=f'sess-{i % 2}',
                consent_state={'analytics': True},
                platform='web',
                locale='pt',
                occurred_at=now - timedelta(days=i),
            )
        AnalyticsEvent.objects.create(
            island=self.island,
            module='news',
            event_type='open',
            properties={},
            session_hash='sess-news',
            consent_state={'analytics': True},
            platform='ios',
            locale='en',
            occurred_at=now - timedelta(days=1),
        )

        for i in range(4):
            Stat.objects.create(
                request='GET_ROUTE',
                origin='Ponta Delgada',
                destination='Ribeira Grande',
                platform='web',
                language='pt',
                type_of_day='WEEKDAY',
            )
        Stat.objects.create(
            request='GET_DIRECTIONS',
            origin='Lagoa',
            destination='Furnas',
            platform='android',
            language='en',
            type_of_day='WEEKEND',
        )

    def _get(self, path, **params):
        params.setdefault('key', AUTH)
        return self.client.get(path, params, HTTP_X_ISLAND=self.island.key)

    def test_requires_auth_key(self):
        resp = self.client.get('/api/v3/analytics/reports/overview', HTTP_X_ISLAND=self.island.key)
        self.assertEqual(resp.status_code, 401)

    def test_v3_overview_totals_and_breakdowns(self):
        resp = self._get('/api/v3/analytics/reports/overview')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['totals']['events'], 6)
        # sess-0, sess-1, sess-news distinct
        self.assertEqual(data['totals']['sessions'], 3)
        modules = {row['key']: row['count'] for row in data['breakdowns']['module']}
        self.assertEqual(modules['transit'], 5)
        self.assertEqual(modules['news'], 1)
        platforms = {row['key']: row['count'] for row in data['breakdowns']['platform']}
        self.assertEqual(platforms['web'], 5)
        self.assertEqual(platforms['ios'], 1)
        self.assertTrue(len(data['series']) >= 1)

    def test_v3_overview_module_filter(self):
        resp = self._get('/api/v3/analytics/reports/overview', module='news')
        data = resp.json()
        self.assertEqual(data['totals']['events'], 1)

    def test_v3_events_pagination(self):
        resp = self._get('/api/v3/analytics/reports/events', page_size=2)
        data = resp.json()
        self.assertEqual(data['count'], 6)
        self.assertEqual(len(data['results']), 2)
        self.assertEqual(data['total_pages'], 3)
        self.assertIn('occurred_at', data['results'][0])

    def test_v3_meta(self):
        resp = self._get('/api/v3/analytics/reports/meta')
        data = resp.json()
        self.assertIn('transit', data['modules'])
        self.assertIn('news', data['modules'])
        self.assertEqual(data['total'], 6)

    def test_legacy_overview_routes(self):
        resp = self._get('/api/v3/analytics/reports/legacy/overview')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['totals']['stats'], 5)
        self.assertEqual(data['totals']['routes'], 5)
        top = data['breakdowns']['top_routes'][0]
        self.assertEqual(top['origin'], 'Ponta Delgada')
        self.assertEqual(top['count'], 4)
        requests_bd = {row['key']: row['count'] for row in data['breakdowns']['request']}
        self.assertEqual(requests_bd['GET_ROUTE'], 4)

    def test_legacy_overview_does_not_require_island(self):
        resp = self.client.get('/api/v3/analytics/reports/legacy/overview', {'key': AUTH})
        self.assertEqual(resp.status_code, 200)

    def test_legacy_events_filter(self):
        resp = self._get('/api/v3/analytics/reports/legacy/events', request='GET_DIRECTIONS')
        data = resp.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['request'], 'GET_DIRECTIONS')

    def test_legacy_meta(self):
        resp = self._get('/api/v3/analytics/reports/legacy/meta')
        data = resp.json()
        self.assertIn('GET_ROUTE', data['requests'])
        self.assertEqual(data['total'], 5)
