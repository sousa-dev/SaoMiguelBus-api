"""The upstream client is the thing that can get us blocked.

Upstream publishes no rate limit and sends no Retry-After or X-RateLimit-*
header at any rate the review tried (98 §6). Absence of a published limit is not
permission, so the pacing, the identifying User-Agent and the hard budget cap are
all enforced here rather than left to the caller.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase

from azoresbus.client import (
    AzoresbusClient,
    AzoresbusError,
    BudgetExhausted,
)


def ok(payload, status=200):
    return MagicMock(ok=True, status_code=status, json=lambda: payload,
                     headers={}, text='')


def err(status, headers=None):
    return MagicMock(ok=False, status_code=status, headers=headers or {},
                     text='upstream said no', json=lambda: {})


class PacingTests(SimpleTestCase):
    @patch('azoresbus.client.time.sleep')
    @patch('azoresbus.client.requests.get')
    def test_requests_are_spaced_and_serial(self, mock_get, mock_sleep):
        mock_get.return_value = ok([])
        client = AzoresbusClient(delay=0.35, jitter=0.0)

        for _ in range(3):
            client.get_json('/stops')

        self.assertEqual(mock_get.call_count, 3)
        # First request does not wait; the next two do.
        slept = [c.args[0] for c in mock_sleep.call_args_list]
        self.assertEqual(len(slept), 2)
        for value in slept:
            self.assertGreaterEqual(value, 0.35)

    @patch('azoresbus.client.time.sleep')
    @patch('azoresbus.client.requests.get')
    def test_identifies_itself(self, mock_get, _sleep):
        mock_get.return_value = ok([])
        AzoresbusClient().get_json('/stops')

        headers = mock_get.call_args.kwargs['headers']
        self.assertIn('SaoMiguelBus', headers['User-Agent'])
        self.assertIn('saomiguelbus.com', headers['User-Agent'])

    @patch('azoresbus.client.time.sleep')
    @patch('azoresbus.client.requests.get')
    def test_delay_cannot_be_set_below_the_floor(self, mock_get, mock_sleep):
        """A caller passing 0 must not turn this into a hammer."""
        mock_get.return_value = ok([])
        client = AzoresbusClient(delay=0.0, jitter=0.0)
        client.get_json('/stops')
        client.get_json('/stops')

        self.assertGreaterEqual(mock_sleep.call_args_list[0].args[0], 0.35)


class BudgetTests(SimpleTestCase):
    @patch('azoresbus.client.time.sleep')
    @patch('azoresbus.client.requests.get')
    def test_budget_cap_stops_the_run(self, mock_get, _sleep):
        mock_get.return_value = ok([])
        client = AzoresbusClient(max_requests=2)

        client.get_json('/stops')
        client.get_json('/stops')
        with self.assertRaises(BudgetExhausted):
            client.get_json('/stops')

        self.assertEqual(mock_get.call_count, 2, 'the third never left')

    @patch('azoresbus.client.time.sleep')
    @patch('azoresbus.client.requests.get')
    def test_request_count_is_observable(self, mock_get, _sleep):
        mock_get.return_value = ok([])
        client = AzoresbusClient()
        client.get_json('/stops')
        client.get_json('/routes/1')
        self.assertEqual(client.request_count, 2)


class BackoffTests(SimpleTestCase):
    @patch('azoresbus.client.time.sleep')
    @patch('azoresbus.client.requests.get')
    def test_429_is_retried_and_retry_after_is_honoured(self, mock_get, mock_sleep):
        mock_get.side_effect = [err(429, {'Retry-After': '7'}), ok([1])]
        client = AzoresbusClient(jitter=0.0)

        self.assertEqual(client.get_json('/stops'), [1])
        self.assertIn(7.0, [c.args[0] for c in mock_sleep.call_args_list])

    @patch('azoresbus.client.time.sleep')
    @patch('azoresbus.client.requests.get')
    def test_5xx_backs_off_exponentially(self, mock_get, mock_sleep):
        mock_get.side_effect = [err(503), err(503), ok(['third time'])]
        client = AzoresbusClient(jitter=0.0)

        self.assertEqual(client.get_json('/stops'), ['third time'])
        waits = [c.args[0] for c in mock_sleep.call_args_list]
        self.assertIn(2.0, waits)
        self.assertIn(4.0, waits)

    @patch('azoresbus.client.time.sleep')
    @patch('azoresbus.client.requests.get')
    def test_gives_up_after_max_attempts(self, mock_get, _sleep):
        mock_get.side_effect = [err(503)] * 6
        client = AzoresbusClient(max_attempts=4, jitter=0.0)

        with self.assertRaises(AzoresbusError):
            client.get_json('/stops')
        self.assertEqual(mock_get.call_count, 4)

    @patch('azoresbus.client.time.sleep')
    @patch('azoresbus.client.requests.get')
    def test_404_is_not_retried(self, mock_get, _sleep):
        """A missing journey is an answer, not a transient failure."""
        mock_get.side_effect = [err(404), ok([])]
        client = AzoresbusClient()

        with self.assertRaises(AzoresbusError):
            client.get_json('/routes/1/journeys/999999')
        self.assertEqual(mock_get.call_count, 1)

    @patch('azoresbus.client.time.sleep')
    @patch('azoresbus.client.requests.get')
    def test_transport_errors_become_domain_errors(self, mock_get, _sleep):
        mock_get.side_effect = requests.RequestException('connection reset')
        client = AzoresbusClient(max_attempts=1)

        with self.assertRaises(AzoresbusError):
            client.get_json('/stops')

    @patch('azoresbus.client.time.sleep')
    @patch('azoresbus.client.requests.get')
    def test_consecutive_failures_abort_the_run(self, mock_get, _sleep):
        """Ten failures in a row means upstream is down, not flaky."""
        mock_get.side_effect = requests.RequestException('down')
        client = AzoresbusClient(max_attempts=1, max_consecutive_failures=3)

        for _ in range(3):
            with self.assertRaises(AzoresbusError):
                client.get_json('/stops')

        with self.assertRaises(AzoresbusError) as ctx:
            client.get_json('/stops')
        self.assertIn('consecutive', str(ctx.exception).lower())

    @patch('azoresbus.client.time.sleep')
    @patch('azoresbus.client.requests.get')
    def test_a_success_resets_the_failure_streak(self, mock_get, _sleep):
        client = AzoresbusClient(max_attempts=1, max_consecutive_failures=3)

        mock_get.side_effect = requests.RequestException('blip')
        for _ in range(2):
            with self.assertRaises(AzoresbusError):
                client.get_json('/stops')

        mock_get.side_effect = None
        mock_get.return_value = ok([])
        client.get_json('/stops')
        self.assertEqual(client.consecutive_failures, 0)
