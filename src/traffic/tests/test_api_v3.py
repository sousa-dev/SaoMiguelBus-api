"""U3 API tests: verbs, ownership 403, tenant isolation, schedule, confirm, throttle."""

from __future__ import annotations

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from tenancy.models import Island
from tenancy.services import get_or_create_default_island
from traffic.models import TrafficCategory, TrafficReport

SM = {'HTTP_X_ISLAND': 'sao-miguel'}


class TrafficAPITests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.island = get_or_create_default_island()
        TrafficCategory.objects.create(
            island=self.island, name='Acidente', slug='acidente', default_ttl_minutes=120,
        )
        TrafficCategory.objects.create(
            island=self.island, name='Radar', slug='radar', default_ttl_minutes=90,
            is_schedulable=True,
        )

    def _create(self, session='owner', slug='acidente', lat=37.78, lng=-25.50, **extra):
        body = {'session_id': session, 'category_slug': slug, 'latitude': lat, 'longitude': lng, **extra}
        return self.client.post('/api/v3/traffic/reports', body, format='json', **SM)

    # --- categories / create ------------------------------------------------

    def test_categories_seeded(self):
        resp = self.client.get('/api/v3/traffic/categories', **SM)
        self.assertEqual(resp.status_code, 200)
        slugs = [c['slug'] for c in resp.json()['categories']]
        self.assertIn('acidente', slugs)
        self.assertIn('radar', slugs)

    def test_create_report_active_and_public_immediately(self):
        resp = self._create()
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['status'], 'active')
        listed = self.client.get('/api/v3/traffic/reports', **SM).json()['reports']
        self.assertEqual(len(listed), 1)

    def test_create_requires_session_and_coords(self):
        no_session = self.client.post(
            '/api/v3/traffic/reports',
            {'session_id': '', 'category_slug': 'acidente', 'latitude': 37.78, 'longitude': -25.50},
            format='json', **SM,
        )
        self.assertEqual(no_session.status_code, 400)
        no_coords = self.client.post(
            '/api/v3/traffic/reports',
            {'session_id': 'x', 'category_slug': 'acidente'},
            format='json', **SM,
        )
        self.assertEqual(no_coords.status_code, 400)

    def test_create_location_implausible(self):
        resp = self._create(lat=40.0, lng=-8.0)  # mainland
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()['error']['code'], 'location_implausible')

    # --- scheduling ---------------------------------------------------------

    def test_scheduled_radar_hidden_then_shown(self):
        future = (timezone.now() + timedelta(hours=2)).isoformat()
        resp = self._create(slug='radar', active_from=future)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['status'], 'scheduled')
        default = self.client.get('/api/v3/traffic/reports', **SM).json()['reports']
        self.assertEqual(default, [])
        with_sched = self.client.get(
            '/api/v3/traffic/reports?include_scheduled=true', **SM
        ).json()['reports']
        self.assertEqual(len(with_sched), 1)

    def test_scheduling_rejected_on_non_schedulable(self):
        future = (timezone.now() + timedelta(hours=2)).isoformat()
        resp = self._create(slug='acidente', active_from=future)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['error']['code'], 'scheduling_not_allowed')

    # --- geo ----------------------------------------------------------------

    def test_list_radius_filters(self):
        self._create(session='a', lat=37.783, lng=-25.50)
        self._create(session='b', lat=37.95, lng=-25.30)
        resp = self.client.get('/api/v3/traffic/reports?lat=37.782&lng=-25.499&radius_km=2', **SM)
        self.assertEqual(len(resp.json()['reports']), 1)

    # --- confirm ------------------------------------------------------------

    def test_confirm_vote_upsert(self):
        rid = self._create().json()['id']
        first = self.client.post(
            f'/api/v3/traffic/reports/{rid}/confirm',
            {'session_id': 'v', 'vote': 'still_there'}, format='json', **SM,
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.json()['confidence']['confirm'], 1)
        second = self.client.post(
            f'/api/v3/traffic/reports/{rid}/confirm',
            {'session_id': 'v', 'vote': 'gone'}, format='json', **SM,
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()['confidence']['confirm'], 0)
        self.assertEqual(second.json()['confidence']['deny'], 1)

    # --- ownership ----------------------------------------------------------

    def test_patch_delete_ownership(self):
        rid = self._create(session='owner').json()['id']
        forbidden = self.client.patch(
            f'/api/v3/traffic/reports/{rid}',
            {'session_id': 'intruder', 'description': 'x'}, format='json', **SM,
        )
        self.assertEqual(forbidden.status_code, 403)
        ok = self.client.patch(
            f'/api/v3/traffic/reports/{rid}',
            {'session_id': 'owner', 'description': 'updated'}, format='json', **SM,
        )
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()['description'], 'updated')
        deleted = self.client.delete(
            f'/api/v3/traffic/reports/{rid}', **{**SM, 'HTTP_X_SESSION_ID': 'owner'}
        )
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(TrafficReport.objects.get(id=rid).status, TrafficReport.REMOVED)

    # --- tenant isolation ---------------------------------------------------

    def test_tenant_isolation(self):
        rid = self._create().json()['id']
        Island.objects.create(
            key='terceira', name='Terceira', center_lat=38.7, center_lng=-27.2,
            radius_km=40, feature_flags={'traffic': True},
        )
        resp = self.client.get(
            f'/api/v3/traffic/reports/{rid}', **{'HTTP_X_ISLAND': 'terceira'}
        )
        self.assertEqual(resp.status_code, 404)

    # --- throttle -----------------------------------------------------------

    def test_write_throttled(self):
        cache.clear()  # traffic_write rate is 30/min
        last = None
        for _ in range(32):
            last = self._create(session='spammer')
        self.assertEqual(last.status_code, 429)
