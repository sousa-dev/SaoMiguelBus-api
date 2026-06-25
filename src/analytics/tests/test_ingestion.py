"""Tests for v3 AnalyticsEvent ingestion and minibus registry validation."""

from django.test import TestCase

from analytics.models import AnalyticsEvent
from analytics.services_events import ingest_events
from consent.models import ConsentRecord
from consent.services import hash_analytics_session_id, hash_session_id
from tenancy.services import get_or_create_default_island


class IngestionTests(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        self.raw_session = 'test-session-123'
        self.consent_hash = hash_session_id(self.raw_session, self.island.key)
        self.analytics_hash = hash_analytics_session_id(self.raw_session, self.island.key)
        ConsentRecord.objects.create(
            session_hash=self.consent_hash,
            purposes={'strictly_necessary': True, 'analytics': True, 'ads': False, 'personalization': False},
            policy_version='1.0.0',
        )

    def _ingest(self, events: list[dict]) -> tuple[int, int]:
        return ingest_events(
            island=self.island,
            events=events,
            session_hash=self.analytics_hash,
            consent_session_hash=self.consent_hash,
            platform='ios',
            locale='pt',
            app_version='5.1.6',
        )

    def test_consent_off_drops_all(self):
        ConsentRecord.objects.all().delete()
        accepted, dropped = self._ingest([
            {
                'module': 'minibus',
                'event_type': 'live_filter',
                'properties': {'line_slug': 'all', 'source': 'chip'},
            },
        ])
        self.assertEqual(accepted, 0)
        self.assertEqual(dropped, 1)
        self.assertEqual(AnalyticsEvent.objects.count(), 0)

    def test_transit_module_passes_through_without_registry(self):
        accepted, dropped = self._ingest([
            {
                'module': 'transit',
                'event_type': 'search',
                'properties': {'origin': 'PDL', 'unexpected_key': 123},
            },
        ])
        self.assertEqual(accepted, 1)
        self.assertEqual(dropped, 0)
        row = AnalyticsEvent.objects.get()
        self.assertEqual(row.module, 'transit')
        self.assertEqual(row.properties['unexpected_key'], 123)

    def test_valid_minibus_live_filter_accepted(self):
        accepted, dropped = self._ingest([
            {
                'module': 'minibus',
                'event_type': 'live_filter',
                'properties': {'line_slug': 'line-a', 'source': 'deep_link', 'extra': 'strip-me'},
            },
        ])
        self.assertEqual(accepted, 1)
        self.assertEqual(dropped, 0)
        row = AnalyticsEvent.objects.get()
        self.assertEqual(row.properties, {'line_slug': 'line-a', 'source': 'deep_link'})

    def test_valid_minibus_live_map_control_accepted(self):
        accepted, dropped = self._ingest([
            {
                'module': 'minibus',
                'event_type': 'live_map_control',
                'properties': {'action': 'center'},
            },
        ])
        self.assertEqual(accepted, 1)
        self.assertEqual(dropped, 0)

    def test_minibus_missing_required_property_dropped(self):
        accepted, dropped = self._ingest([
            {
                'module': 'minibus',
                'event_type': 'live_map_control',
                'properties': {},
            },
        ])
        self.assertEqual(accepted, 0)
        self.assertEqual(dropped, 1)

    def test_minibus_invalid_enum_dropped(self):
        accepted, dropped = self._ingest([
            {
                'module': 'minibus',
                'event_type': 'live_map_control',
                'properties': {'action': 'pan'},
            },
        ])
        self.assertEqual(accepted, 0)
        self.assertEqual(dropped, 1)

    def test_minibus_unknown_event_type_dropped(self):
        accepted, dropped = self._ingest([
            {
                'module': 'minibus',
                'event_type': 'not_real',
                'properties': {'foo': 'bar'},
            },
        ])
        self.assertEqual(accepted, 0)
        self.assertEqual(dropped, 1)

    def test_minibus_live_select_requires_source_and_one_key(self):
        accepted, dropped = self._ingest([
            {
                'module': 'minibus',
                'event_type': 'live_select',
                'properties': {'vehicle_id': 'bus-1'},
            },
        ])
        self.assertEqual(accepted, 0)
        self.assertEqual(dropped, 1)

        accepted, dropped = self._ingest([
            {
                'module': 'minibus',
                'event_type': 'live_select',
                'properties': {
                    'vehicle_id': 'bus-1',
                    'source': 'map',
                },
            },
        ])
        self.assertEqual(accepted, 1)
        self.assertEqual(dropped, 0)

    def test_batch_partial_accept_counts(self):
        accepted, dropped = self._ingest([
            {
                'module': 'minibus',
                'event_type': 'live_health',
                'properties': {'action': 'retry'},
            },
            {
                'module': 'minibus',
                'event_type': 'live_health',
                'properties': {'action': 'invalid'},
            },
            {
                'module': '',
                'event_type': 'view',
                'properties': {},
            },
        ])
        self.assertEqual(accepted, 1)
        self.assertEqual(dropped, 2)
        self.assertEqual(AnalyticsEvent.objects.count(), 1)

    def test_minibus_search_accepted(self):
        accepted, dropped = self._ingest([
            {
                'module': 'minibus',
                'event_type': 'search',
                'properties': {
                    'origin': 'PDL',
                    'destination': 'Ribeira Grande',
                    'results_count': 2,
                    'offline': False,
                    'source': 'api',
                },
            },
        ])
        self.assertEqual(accepted, 1)
        self.assertEqual(dropped, 0)
