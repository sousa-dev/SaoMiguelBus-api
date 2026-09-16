"""The AI scope is shared by all callers at one IP, including signed-in users."""

from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase

from assistant.throttling import AIThrottle


class AIThrottleTestCase(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_different_authenticated_users_at_same_ip_share_bucket(self):
        view = SimpleNamespace()
        first = SimpleNamespace(
            user=SimpleNamespace(pk=101, is_authenticated=True),
            META={'REMOTE_ADDR': '203.0.113.8'},
        )
        second = SimpleNamespace(
            user=SimpleNamespace(pk=202, is_authenticated=True),
            META={'REMOTE_ADDR': '203.0.113.8'},
        )
        with patch.object(AIThrottle, 'THROTTLE_RATES', {'ai': '1/min'}):
            self.assertTrue(AIThrottle().allow_request(first, view))
            self.assertFalse(AIThrottle().allow_request(second, view))
