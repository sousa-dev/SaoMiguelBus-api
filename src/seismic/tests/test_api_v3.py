"""Seismic v3 API tests."""

from datetime import datetime, timedelta, timezone as dt_timezone

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from seismic.models import FeltReport, SeismicEvent
from tenancy.services import get_or_create_default_island


class SeismicAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.island = get_or_create_default_island()
        self.island.feature_flags = {
            **self.island.feature_flags,
            'seismic': True,
            'transit': True,
        }
        self.island.save()
        self.headers = {'HTTP_X_ISLAND': 'sao-miguel'}
        self.event = SeismicEvent.objects.create(
            island=self.island,
            emsc_id='20260601_0000099',
            magnitude=4.1,
            depth_km=10.0,
            latitude=37.78,
            longitude=-25.50,
            occurred_at=datetime(2026, 6, 1, 12, 0, tzinfo=dt_timezone.utc),
            region='AZORES',
        )

    def test_list_events_ordered(self):
        older = SeismicEvent.objects.create(
            island=self.island,
            emsc_id='older_event',
            magnitude=2.5,
            latitude=37.0,
            longitude=-25.0,
            occurred_at=datetime(2026, 5, 1, 12, 0, tzinfo=dt_timezone.utc),
        )
        response = self.client.get(
            '/api/v3/seismic/events?since_hours=0', **self.headers
        )
        self.assertEqual(response.status_code, 200)
        events = response.json()['events']
        self.assertEqual(events[0]['id'], self.event.id)
        self.assertEqual(events[1]['id'], older.id)

    def test_list_default_24h_excludes_old_event(self):
        response = self.client.get('/api/v3/seismic/events', **self.headers)
        self.assertEqual(response.status_code, 200)
        ids = [e['id'] for e in response.json()['events']]
        self.assertNotIn(self.event.id, ids)

    def test_list_since_hours_includes_old_event(self):
        response = self.client.get(
            '/api/v3/seismic/events?since_hours=168', **self.headers
        )
        self.assertEqual(response.status_code, 200)
        ids = [e['id'] for e in response.json()['events']]
        self.assertIn(self.event.id, ids)

    def test_list_invalid_since_hours(self):
        response = self.client.get(
            '/api/v3/seismic/events?since_hours=abc', **self.headers
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], 'invalid_since_hours')

    def test_list_recent_event_within_24h(self):
        recent = SeismicEvent.objects.create(
            island=self.island,
            emsc_id='recent_event',
            magnitude=3.0,
            latitude=37.8,
            longitude=-25.5,
            occurred_at=timezone.now() - timedelta(hours=2),
            region='AZORES',
        )
        response = self.client.get('/api/v3/seismic/events', **self.headers)
        self.assertEqual(response.status_code, 200)
        ids = [e['id'] for e in response.json()['events']]
        self.assertIn(recent.id, ids)
        self.assertNotIn(self.event.id, ids)

    def test_detail_includes_felt_counts(self):
        FeltReport.objects.create(
            island=self.island,
            event=self.event,
            session_hash='hash-a',
            felt=True,
            intensity=5,
        )
        FeltReport.objects.create(
            island=self.island,
            event=self.event,
            session_hash='hash-b',
            felt=False,
        )
        response = self.client.get(f'/api/v3/seismic/events/{self.event.id}', **self.headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['feltYesCount'], 1)
        self.assertEqual(body['feltNoCount'], 1)
        self.assertEqual(body['feltCount'], 1)
        self.assertEqual(body['feltSummary']['5'], 1)

    def test_post_felt_creates_report(self):
        response = self.client.post(
            f'/api/v3/seismic/events/{self.event.id}/felt',
            {'session_id': 'session-abc', 'felt': True, 'intensity': 6},
            format='json',
            **self.headers,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(FeltReport.objects.count(), 1)
        body = response.json()
        self.assertEqual(body['feltYesCount'], 1)
        self.assertEqual(body['feltNoCount'], 0)

    def test_post_felt_not_felt(self):
        response = self.client.post(
            f'/api/v3/seismic/events/{self.event.id}/felt',
            {'session_id': 'session-abc', 'felt': False},
            format='json',
            **self.headers,
        )
        self.assertEqual(response.status_code, 201)
        report = FeltReport.objects.get()
        self.assertFalse(report.felt)
        self.assertIsNone(report.intensity)
        body = response.json()
        self.assertEqual(body['feltYesCount'], 0)
        self.assertEqual(body['feltNoCount'], 1)

    def test_post_felt_upserts_intensity(self):
        self.client.post(
            f'/api/v3/seismic/events/{self.event.id}/felt',
            {'session_id': 'session-abc', 'felt': True, 'intensity': 4},
            format='json',
            **self.headers,
        )
        response = self.client.post(
            f'/api/v3/seismic/events/{self.event.id}/felt',
            {'session_id': 'session-abc', 'felt': True, 'intensity': 7},
            format='json',
            **self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(FeltReport.objects.count(), 1)
        self.assertEqual(FeltReport.objects.get().intensity, 7)

    def test_post_felt_upsert_yes_to_no(self):
        self.client.post(
            f'/api/v3/seismic/events/{self.event.id}/felt',
            {'session_id': 'session-abc', 'felt': True, 'intensity': 4},
            format='json',
            **self.headers,
        )
        response = self.client.post(
            f'/api/v3/seismic/events/{self.event.id}/felt',
            {'session_id': 'session-abc', 'felt': False},
            format='json',
            **self.headers,
        )
        self.assertEqual(response.status_code, 200)
        report = FeltReport.objects.get()
        self.assertFalse(report.felt)
        self.assertIsNone(report.intensity)

    def test_post_felt_requires_session(self):
        response = self.client.post(
            f'/api/v3/seismic/events/{self.event.id}/felt',
            {'felt': True, 'intensity': 5},
            format='json',
            **self.headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_post_felt_requires_felt_field(self):
        response = self.client.post(
            f'/api/v3/seismic/events/{self.event.id}/felt',
            {'session_id': 'session-abc', 'intensity': 5},
            format='json',
            **self.headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_post_felt_invalid_intensity(self):
        response = self.client.post(
            f'/api/v3/seismic/events/{self.event.id}/felt',
            {'session_id': 'session-abc', 'felt': True, 'intensity': 13},
            format='json',
            **self.headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_post_felt_unknown_event(self):
        response = self.client.post(
            '/api/v3/seismic/events/99999/felt',
            {'session_id': 'session-abc', 'felt': True, 'intensity': 5},
            format='json',
            **self.headers,
        )
        self.assertEqual(response.status_code, 404)
