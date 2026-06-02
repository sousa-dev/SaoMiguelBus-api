"""News RSS poll and v3 API tests."""

from datetime import datetime, timezone as dt_timezone
from unittest.mock import MagicMock, patch

from django.test import TestCase
from rest_framework.test import APIClient

from news.models import NewsArticle, NewsSource
from news.services import poll_source
from tenancy.services import get_or_create_default_island


class NewsServicesTestCase(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        self.island.is_live = True
        self.island.feature_flags = {**self.island.feature_flags, 'news': True, 'transit': True}
        self.island.save()
        self.source = NewsSource.objects.create(
            island=self.island,
            name='Test Feed',
            rss_url='https://example.com/rss.xml',
            language='pt',
            active=True,
        )

    @patch('news.services.feedparser.parse')
    def test_poll_source_dedupes_by_link(self, mock_parse):
        mock_parse.return_value = MagicMock(
            entries=[
                {
                    'title': 'Article One',
                    'link': 'https://example.com/a1',
                    'summary': 'Summary',
                    'published_parsed': (2026, 6, 1, 10, 0, 0, 0, 0, 0),
                },
                {
                    'title': 'Article One duplicate',
                    'link': 'https://example.com/a1',
                    'summary': 'Summary',
                    'published_parsed': (2026, 6, 1, 11, 0, 0, 0, 0, 0),
                },
            ],
        )
        created, skipped = poll_source(self.source)
        self.assertEqual(created, 1)
        self.assertEqual(skipped, 1)
        self.assertEqual(NewsArticle.objects.count(), 1)


class NewsAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.island = get_or_create_default_island()
        self.island.is_live = True
        self.island.feature_flags = {**self.island.feature_flags, 'news': True, 'transit': True}
        self.island.save()
        self.headers = {'HTTP_X_ISLAND': 'sao-miguel'}
        self.source = NewsSource.objects.create(
            island=self.island,
            name='API Feed',
            rss_url='https://example.com/api.xml',
            language='pt',
        )
        self.article = NewsArticle.objects.create(
            island=self.island,
            source=self.source,
            title='Azores headline',
            summary='Short summary',
            link='https://example.com/story',
            published_at=datetime(2026, 6, 1, 12, 0, tzinfo=dt_timezone.utc),
            category='local',
            content_hash='abc123',
        )

    def test_list_articles(self):
        response = self.client.get('/api/v3/news/articles', **self.headers)
        self.assertEqual(response.status_code, 200)
        articles = response.json()['articles']
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]['title'], 'Azores headline')

    def test_list_articles_filter_category(self):
        response = self.client.get('/api/v3/news/articles?category=other', **self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['articles']), 0)

    def test_article_detail(self):
        response = self.client.get(f'/api/v3/news/articles/{self.article.id}', **self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['link'], 'https://example.com/story')
