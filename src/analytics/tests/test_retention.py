"""Analytics retention task tests."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from analytics.models import AnalyticsEvent
from analytics.tasks import anonymize_analytics_events_task
from tenancy.services import get_or_create_default_island


class AnalyticsRetentionTestCase(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()

    def test_anonymize_old_events(self):
        old_time = timezone.now() - timedelta(days=500)
        event = AnalyticsEvent.objects.create(
            island=self.island,
            module='transit',
            event_type='search',
            properties={'origin': 'Ponta Delgada', 'destination': 'Ribeira Grande'},
            session_hash='abc123',
            consent_state={'analytics': True},
            platform='web',
            locale='pt',
            occurred_at=old_time,
        )

        result = anonymize_analytics_events_task(island_key=self.island.key)
        self.assertGreaterEqual(result['anonymized'], 1)

        event.refresh_from_db()
        self.assertEqual(event.session_hash, '')
        self.assertNotIn('origin', event.properties)
        self.assertNotIn('destination', event.properties)
