"""Seismic v3 API tests."""

from datetime import datetime, timezone as dt_timezone

from django.test import TestCase
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
        response = self.client.get('/api/v3/seismic/events', **self.headers)
        self.assertEqual(response.status_code, 200)
        events = response.json()['events']
        self.assertEqual(events[0]['id'], self.event.id)
        self.assertEqual(events[1]['id'], older.id)

    def test_detail_includes_felt_count(self):
        FeltReport.objects.create(
            island=self.island,
            event=self.event,
            session_hash='hash-a',
            intensity=5,
        )
        response = self.client.get(f'/api/v3/seismic/events/{self.event.id}', **self.headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['feltCount'], 1)
        self.assertEqual(body['feltSummary']['5'], 1)

    def test_post_felt_creates_report(self):
        response = self.client.post(
            f'/api/v3/seismic/events/{self.event.id}/felt',
            {'session_id': 'session-abc', 'intensity': 6},
            format='json',
            **self.headers,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(FeltReport.objects.count(), 1)

    def test_post_felt_upserts_intensity(self):
        self.client.post(
            f'/api/v3/seismic/events/{self.event.id}/felt',
            {'session_id': 'session-abc', 'intensity': 4},
            format='json',
            **self.headers,
        )
        response = self.client.post(
            f'/api/v3/seismic/events/{self.event.id}/felt',
            {'session_id': 'session-abc', 'intensity': 7},
            format='json',
            **self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(FeltReport.objects.count(), 1)
        self.assertEqual(FeltReport.objects.get().intensity, 7)

    def test_post_felt_requires_session(self):
        response = self.client.post(
            f'/api/v3/seismic/events/{self.event.id}/felt',
            {'intensity': 5},
            format='json',
            **self.headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_post_felt_invalid_intensity(self):
        response = self.client.post(
            f'/api/v3/seismic/events/{self.event.id}/felt',
            {'session_id': 'session-abc', 'intensity': 13},
            format='json',
            **self.headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_post_felt_unknown_event(self):
        response = self.client.post(
            '/api/v3/seismic/events/99999/felt',
            {'session_id': 'session-abc', 'intensity': 5},
            format='json',
            **self.headers,
        )
        self.assertEqual(response.status_code, 404)
