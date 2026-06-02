"""Viator tours proxy tests."""

from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from events.services import serialize_tour_summary
from events.viator_client import ViatorNotConfigured
from tenancy.services import get_or_create_default_island


SAMPLE_PRODUCT = {
    'status': 'ACTIVE',
    'productCode': 'ABC123',
    'title': 'Whale Watching',
    'productUrl': 'https://www.viator.com/tours/Sao-Miguel/Whale/d123-ABC123',
    'reviews': {'combinedAverageRating': 4.8, 'totalReviews': 120},
    'pricing': {'currency': 'EUR', 'summary': {'fromPrice': 55.0}},
    'duration': {'fixedDurationInMinutes': 180},
    'images': [
        {
            'isCover': True,
            'variants': [
                {'url': 'https://cdn.example/small.jpg', 'width': 100, 'height': 100},
                {'url': 'https://cdn.example/large.jpg', 'width': 400, 'height': 300},
            ],
        },
    ],
}


class ToursServicesTestCase(TestCase):
    def test_serialize_tour_summary_maps_fields(self):
        out = serialize_tour_summary(SAMPLE_PRODUCT)
        self.assertEqual(out['code'], 'ABC123')
        self.assertEqual(out['title'], 'Whale Watching')
        self.assertEqual(out['thumbnailUrl'], 'https://cdn.example/large.jpg')
        self.assertEqual(out['rating'], 4.8)
        self.assertEqual(out['reviewCount'], 120)
        self.assertEqual(out['fromPrice'], 55.0)
        self.assertEqual(out['currency'], 'EUR')
        self.assertEqual(out['durationMinutes'], 180)
        self.assertIn('pid=', out['bookingUrl'])

    @override_settings(
        CACHES={
            'default': {
                'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            }
        }
    )
    @patch('events.services.search_products')
    @patch('events.services.resolve_destination_id', return_value='99')
    def test_list_tours_uses_cache(self, _mock_dest, mock_search):
        mock_search.return_value = {'products': [SAMPLE_PRODUCT]}
        from events.services import list_tours

        first = list_tours(locale='en')
        second = list_tours(locale='en')
        self.assertEqual(len(first), 1)
        self.assertEqual(first, second)
        self.assertEqual(mock_search.call_count, 1)


class ToursAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.island = get_or_create_default_island()
        self.island.is_live = True
        self.island.feature_flags = {**self.island.feature_flags, 'events': True, 'transit': True}
        self.island.save()
        self.headers = {'HTTP_X_ISLAND': 'sao-miguel'}

    @patch('events.api_v3.list_tours')
    def test_tours_list(self, mock_list):
        mock_list.return_value = [serialize_tour_summary(SAMPLE_PRODUCT)]
        response = self.client.get('/api/v3/events/tours', **self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['tours']), 1)
        self.assertEqual(response.json()['tours'][0]['code'], 'ABC123')

    @patch('events.api_v3.get_tour')
    def test_tour_detail(self, mock_get):
        from events.services import serialize_tour_detail

        mock_get.return_value = serialize_tour_detail(
            {**SAMPLE_PRODUCT, 'description': 'Great tour', 'flags': ['FREE_CANCELLATION']},
        )
        response = self.client.get('/api/v3/events/tours/ABC123', **self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['code'], 'ABC123')
        self.assertIn('description', response.json())

    @patch('events.api_v3.list_tours', side_effect=ViatorNotConfigured('no key'))
    def test_viator_unavailable(self, _mock):
        response = self.client.get('/api/v3/events/tours', **self.headers)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()['error']['code'], 'viator_unavailable')
