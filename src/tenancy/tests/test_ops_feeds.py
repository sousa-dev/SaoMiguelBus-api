"""Ops feed sync trigger tests."""

from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, override_settings
from rest_framework.test import APIClient


@override_settings(AUTH_KEY='test-auth-key')
class OpsFeedSyncTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = '/api/v1/ops/feeds/sync'
        self.auth = {'QUERY_STRING': f'key={settings.AUTH_KEY}'}

    def test_requires_auth_key(self):
        response = self.client.post(f'{self.url}?feed=news')
        self.assertEqual(response.status_code, 401)

    def test_invalid_feed(self):
        response = self.client.post(f'{self.url}?key={settings.AUTH_KEY}&feed=bad')
        self.assertEqual(response.status_code, 400)

    @patch('shared.feed_syncs.run_feed_sync')
    def test_sync_trails_inline(self, mock_run):
        mock_run.return_value = {
            'status': 'ok',
            'islands': 1,
            'trails_created': 2,
            'trails_updated': 0,
            'pois_created': 0,
            'pois_updated': 0,
            'skipped': 0,
        }
        response = self.client.post(
            f'{self.url}?key={settings.AUTH_KEY}&feed=trails&island=sao-miguel',
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['ok'])
        self.assertFalse(body['async'])
        self.assertEqual(body['feeds']['trails']['mode'], 'sync')
        self.assertEqual(body['feeds']['trails']['trails_created'], 2)
        mock_run.assert_called_once_with('trails', island_key='sao-miguel')

    @patch('shared.feed_syncs.queue_feed_sync')
    def test_async_queues_celery(self, mock_queue):
        mock_queue.return_value = {
            'task': 'trails.sync_open_data',
            'celery_task_id': 'abc-123',
        }
        response = self.client.post(
            f'{self.url}?key={settings.AUTH_KEY}&feed=trails&async=true',
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['async'])
        self.assertEqual(body['feeds']['trails']['celery_task_id'], 'abc-123')

    @patch('shared.feed_syncs.run_feed_sync')
    def test_sync_all_feeds(self, mock_run):
        mock_run.return_value = {'status': 'ok', 'created': 0}
        response = self.client.get(f'{self.url}?key={settings.AUTH_KEY}&feed=all')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_run.call_count, 3)

    @patch('shared.feed_syncs.run_feed_sync', side_effect=RuntimeError('boom'))
    def test_sync_error_returns_502(self, _mock_run):
        response = self.client.post(f'{self.url}?key={settings.AUTH_KEY}&feed=news')
        self.assertEqual(response.status_code, 502)
        body = response.json()
        self.assertFalse(body['ok'])
        self.assertEqual(body['feeds']['news']['error_type'], 'RuntimeError')
