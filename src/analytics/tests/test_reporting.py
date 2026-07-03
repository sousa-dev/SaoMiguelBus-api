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

    def _make_search(self, origin, destination, **extra):
        props = {'origin': origin, 'destination': destination}
        props.update(extra)
        AnalyticsEvent.objects.create(
            island=self.island,
            module='transit',
            event_type='search',
            properties=props,
            session_hash='s',
            consent_state={'analytics': True},
            platform='web',
            locale='pt',
            occurred_at=timezone.now(),
        )

    def test_v3_properties_breakdowns_and_routes(self):
        for _ in range(3):
            self._make_search('Ponta Delgada', 'Furnas', day_type='weekday', results_count=2)
        self._make_search('Lagoa', 'Furnas', day_type='sunday', results_count=0)

        resp = self._get('/api/v3/analytics/reports/properties', module='transit', event_type='search')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        origins = {r['key']: r['count'] for r in data['breakdowns']['origin']}
        self.assertEqual(origins['Ponta Delgada'], 3)
        self.assertEqual(origins['Lagoa'], 1)

        dests = {r['key']: r['count'] for r in data['breakdowns']['destination']}
        self.assertEqual(dests['Furnas'], 4)

        top_route = data['routes'][0]
        self.assertEqual(top_route['origin'], 'Ponta Delgada')
        self.assertEqual(top_route['destination'], 'Furnas')
        self.assertEqual(top_route['count'], 3)

        # day_type and results_count are discovered too
        self.assertIn('day_type', data['breakdowns'])
        self.assertIn('results_count', data['breakdowns'])

    def test_v3_properties_single_key(self):
        self._make_search('Vila Franca', 'Nordeste')
        self._make_search('Vila Franca', 'Furnas')
        resp = self._get('/api/v3/analytics/reports/properties', module='transit', prop='origin')
        data = resp.json()
        self.assertEqual(data['key'], 'origin')
        values = {r['key']: r['count'] for r in data['values']}
        self.assertEqual(values['Vila Franca'], 2)

    def test_v3_properties_skips_coordinates(self):
        AnalyticsEvent.objects.create(
            island=self.island, module='trails', event_type='weather_view',
            properties={'lat': 37.8387, 'lng': -25.3624}, session_hash='s',
            consent_state={'analytics': True}, platform='web', locale='pt',
            occurred_at=timezone.now(),
        )
        resp = self._get('/api/v3/analytics/reports/properties', module='trails')
        data = resp.json()
        self.assertNotIn('lat', data.get('breakdowns', {}))
        self.assertNotIn('lng', data.get('breakdowns', {}))

    def test_legacy_overview_time_breakdown(self):
        Stat.objects.create(request='GET_ROUTE', origin='A', destination='B',
                            platform='web', language='pt', time='08:00')
        Stat.objects.create(request='GET_ROUTE', origin='A', destination='B',
                            platform='web', language='pt', time='08:00')
        resp = self._get('/api/v3/analytics/reports/legacy/overview')
        data = resp.json()
        times = {r['key']: r['count'] for r in data['breakdowns']['time']}
        self.assertEqual(times.get('08:00'), 2)
        self.assertNotIn('NA', times)

    def test_v3_overview_compare_previous_period(self):
        now = timezone.now()
        # Current window: last 3 days (5 setUp events at day 0..4 → days 0-2 inside).
        start = (now - timedelta(days=3)).date().isoformat()
        end = now.date().isoformat()
        resp = self._get('/api/v3/analytics/reports/overview', start=start, end=end, compare=1)
        data = resp.json()
        self.assertIn('previous', data)
        self.assertIn('totals', data['previous'])
        self.assertIn('series', data['previous'])
        # Previous window covers days 3-6 → the 2 older transit events.
        self.assertGreaterEqual(data['previous']['totals']['events'], 1)

    def test_v3_overview_without_compare_has_no_previous(self):
        resp = self._get('/api/v3/analytics/reports/overview')
        self.assertNotIn('previous', resp.json())

    def test_v3_overview_property_filter(self):
        self._make_search('Lagoa', 'Nordeste')
        resp = self._get('/api/v3/analytics/reports/overview', **{'prop.origin': 'Lagoa'})
        data = resp.json()
        self.assertEqual(data['totals']['events'], 1)

    def test_v3_events_property_filter(self):
        self._make_search('Lagoa', 'Nordeste')
        self._make_search('Furnas', 'Lagoa')
        resp = self._get('/api/v3/analytics/reports/events', **{'prop.origin': 'Lagoa'})
        data = resp.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['properties']['origin'], 'Lagoa')

    def test_v3_overview_locale_filter(self):
        resp = self._get('/api/v3/analytics/reports/overview', locale='en')
        data = resp.json()
        self.assertEqual(data['totals']['events'], 1)

    def test_legacy_overview_origin_filter(self):
        resp = self._get('/api/v3/analytics/reports/legacy/overview', origin='Lagoa')
        data = resp.json()
        self.assertEqual(data['totals']['stats'], 1)
        self.assertEqual(data['breakdowns']['top_destinations'][0]['key'], 'Furnas')

    def test_legacy_events_destination_filter(self):
        resp = self._get('/api/v3/analytics/reports/legacy/events', destination='Furnas')
        data = resp.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['origin'], 'Lagoa')

    def test_legacy_overview_compare(self):
        resp = self._get('/api/v3/analytics/reports/legacy/overview', compare=1)
        data = resp.json()
        self.assertIn('previous', data)
        self.assertEqual(data['previous']['totals']['stats'], 0)


@override_settings(AUTH_KEY=AUTH)
class UnifiedTransitReportTests(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        now = timezone.now()
        for _ in range(3):
            Stat.objects.create(
                request='GET_ROUTE', origin='Ponta Delgada', destination='Furnas',
                platform='android', language='pt',
            )
        Stat.objects.create(
            request='GET_ROUTE', origin='Lagoa', destination='Nordeste',
            platform='web', language='en',
        )
        # Non-route stat rows must not count as searches.
        Stat.objects.create(request='GET_AD', platform='web', language='pt')
        for _ in range(2):
            AnalyticsEvent.objects.create(
                island=self.island, module='transit', event_type='search',
                properties={'origin': 'Ponta Delgada', 'destination': 'Furnas'},
                session_hash='s', consent_state={'analytics': True},
                platform='web', locale='pt', occurred_at=now,
            )
        # Other transit events must not count as searches.
        AnalyticsEvent.objects.create(
            island=self.island, module='transit', event_type='view',
            properties={}, session_hash='s', consent_state={'analytics': True},
            platform='web', locale='pt', occurred_at=now,
        )

    def _get(self, **params):
        params.setdefault('key', AUTH)
        return self.client.get(
            '/api/v3/analytics/reports/transit/overview', params, HTTP_X_ISLAND=self.island.key
        )

    def test_totals_merge_both_sources(self):
        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['totals'], {'searches': 6, 'legacy': 4, 'v3': 2})

    def test_top_routes_merged_across_sources(self):
        data = self._get().json()
        top = data['breakdowns']['top_routes'][0]
        self.assertEqual(top['origin'], 'Ponta Delgada')
        self.assertEqual(top['destination'], 'Furnas')
        self.assertEqual(top['count'], 5)  # 3 legacy + 2 v3

    def test_origin_filter_applies_to_both_sources(self):
        data = self._get(origin='Ponta Delgada').json()
        self.assertEqual(data['totals'], {'searches': 5, 'legacy': 3, 'v3': 2})

    def test_platform_breakdown_merged(self):
        data = self._get().json()
        platforms = {r['key']: r['count'] for r in data['breakdowns']['platform']}
        self.assertEqual(platforms['web'], 3)  # 1 legacy + 2 v3
        self.assertEqual(platforms['android'], 3)

    def test_series_has_source_split(self):
        data = self._get().json()
        self.assertTrue(data['series'])
        row = data['series'][-1]
        self.assertEqual(row['total'], row['legacy'] + row['v3'])

    def test_compare_block(self):
        data = self._get(compare=1).json()
        self.assertIn('previous', data)
        self.assertEqual(data['previous']['totals']['searches'], 0)

    def test_requires_auth(self):
        resp = self.client.get(
            '/api/v3/analytics/reports/transit/overview', HTTP_X_ISLAND=self.island.key
        )
        self.assertEqual(resp.status_code, 401)
