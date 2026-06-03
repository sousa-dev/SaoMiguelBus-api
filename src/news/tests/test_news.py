"""News RSS poll and v3 API tests."""

from datetime import datetime, timezone as dt_timezone
from unittest.mock import MagicMock, patch

from django.test import TestCase
from rest_framework.test import APIClient

from news.models import NewsArticle, NewsSource, NewsSourceKind
from news.services import poll_source
from news.tests.test_azores_adapter import ALRA_FIXTURE, JORAA_FIXTURE
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
    def test_poll_source_dedupes_by_content_hash(self, mock_parse):
        mock_parse.return_value = MagicMock(
            entries=[
                {
                    'title': 'Article One',
                    'link': 'https://example.com/a1',
                    'summary': 'Summary',
                    'published_parsed': (2026, 6, 1, 10, 0, 0, 0, 0, 0),
                },
                {
                    'title': 'Article One',
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

    @patch('news.services.feedparser.parse')
    def test_azores_digest_creates_one_article_per_item(self, mock_parse):
        self.source.kind = NewsSourceKind.AZORES_DIGEST
        self.source.default_category = 'noticias'
        self.source.save()

        mock_parse.return_value = MagicMock(
            entries=[
                {
                    'title': 'Atualização (ALRA) - 2026-06-02',
                    'link': 'https://xn--aores-yra.net/alra_updates/2026-06-02',
                    'description': ALRA_FIXTURE,
                    'published_parsed': (2026, 6, 2, 23, 59, 59, 0, 0, 0),
                },
            ],
        )
        created, skipped = poll_source(self.source)
        self.assertEqual(created, 3)
        self.assertEqual(skipped, 0)
        self.assertEqual(NewsArticle.objects.count(), 3)
        self.assertTrue(all(a.category == 'noticias' for a in NewsArticle.objects.all()))

    @patch('news.services.feedparser.parse')
    def test_azores_digest_repoll_skips_identical_items(self, mock_parse):
        self.source.kind = NewsSourceKind.AZORES_DIGEST
        self.source.default_category = 'noticias'
        self.source.save()

        entry = {
            'title': 'Atualização (ALRA) - 2026-06-02',
            'link': 'https://xn--aores-yra.net/alra_updates/2026-06-02',
            'description': ALRA_FIXTURE,
            'published_parsed': (2026, 6, 2, 23, 59, 59, 0, 0, 0),
        }
        mock_parse.return_value = MagicMock(entries=[entry])
        created, _ = poll_source(self.source)
        self.assertEqual(created, 3)

        created, skipped = poll_source(self.source)
        self.assertEqual(created, 0)
        self.assertEqual(skipped, 3)
        self.assertEqual(NewsArticle.objects.count(), 3)

    @patch('news.services.feedparser.parse')
    def test_azores_digest_state_change_creates_new_article(self, mock_parse):
        self.source.kind = NewsSourceKind.AZORES_DIGEST
        self.source.default_category = 'noticias'
        self.source.save()

        mock_parse.return_value = MagicMock(
            entries=[
                {
                    'title': 'Atualização (ALRA) - 2026-06-01',
                    'link': 'https://xn--aores-yra.net/alra_updates/2026-06-01',
                    'description': ALRA_FIXTURE,
                    'published_parsed': (2026, 6, 1, 23, 59, 59, 0, 0, 0),
                },
            ],
        )
        poll_source(self.source)
        initial_count = NewsArticle.objects.count()

        changed_fixture = ALRA_FIXTURE.replace(
            'NO PRAZO → RESPOSTA ATEMPADA',
            'NO PRAZO → RESPOSTA TADIA',
            1,
        )
        mock_parse.return_value = MagicMock(
            entries=[
                {
                    'title': 'Atualização (ALRA) - 2026-06-02',
                    'link': 'https://xn--aores-yra.net/alra_updates/2026-06-02',
                    'description': changed_fixture,
                    'published_parsed': (2026, 6, 2, 23, 59, 59, 0, 0, 0),
                },
            ],
        )
        created, _ = poll_source(self.source)
        self.assertGreater(NewsArticle.objects.count(), initial_count)
        self.assertGreaterEqual(created, 1)

    @patch('news.services.feedparser.parse')
    def test_azores_digest_empty_parse_falls_back_to_generic(self, mock_parse):
        self.source.kind = NewsSourceKind.AZORES_DIGEST
        self.source.default_category = 'noticias'
        self.source.save()

        mock_parse.return_value = MagicMock(
            entries=[
                {
                    'title': 'Digest fallback',
                    'link': 'https://example.com/digest',
                    'description': '<p>no parseable items</p>',
                    'published_parsed': (2026, 6, 1, 10, 0, 0, 0, 0, 0),
                },
            ],
        )
        created, skipped = poll_source(self.source)
        self.assertEqual(created, 1)
        self.assertEqual(skipped, 0)
        article = NewsArticle.objects.get()
        self.assertEqual(article.title, 'Digest fallback')

    @patch('news.services.feedparser.parse')
    def test_joraa_digest_uses_pagamentos_category(self, mock_parse):
        joraa = NewsSource.objects.create(
            island=self.island,
            name='JORAA (Açores)',
            rss_url='https://xn--aores-yra.net/rss/joraa.xml',
            language='pt',
            kind=NewsSourceKind.AZORES_DIGEST,
            default_category='pagamentos',
            active=True,
        )
        mock_parse.return_value = MagicMock(
            entries=[
                {
                    'title': 'Atualização (JORAA) - 2026-06-02',
                    'link': 'https://xn--aores-yra.net/joraa_updates/2026-06-02',
                    'description': JORAA_FIXTURE,
                    'published_parsed': (2026, 6, 2, 23, 59, 59, 0, 0, 0),
                },
            ],
        )
        created, _ = poll_source(joraa)
        self.assertEqual(created, 2)
        self.assertTrue(all(a.category == 'pagamentos' for a in NewsArticle.objects.filter(source=joraa)))


class NewsAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.island = get_or_create_default_island()
        self.island.is_live = True
        self.island.feature_flags = {**self.island.feature_flags, 'news': True, 'transit': True}
        self.island.save()
        self.headers = {'HTTP_X_ISLAND': 'sao-miguel'}
        self.alra_source = NewsSource.objects.create(
            island=self.island,
            name='ALRA (Açores)',
            rss_url='https://xn--aores-yra.net/rss/alra.xml',
            language='pt',
            kind=NewsSourceKind.AZORES_DIGEST,
            default_category='noticias',
        )
        self.joraa_source = NewsSource.objects.create(
            island=self.island,
            name='JORAA (Açores)',
            rss_url='https://xn--aores-yra.net/rss/joraa.xml',
            language='pt',
            kind=NewsSourceKind.AZORES_DIGEST,
            default_category='pagamentos',
        )
        self.noticias_article = NewsArticle.objects.create(
            island=self.island,
            source=self.alra_source,
            title='ALRA headline',
            summary='Requerimento summary',
            link='http://base.alra.pt:82/4DACTION/w_pesquisa_registo/4/9280',
            published_at=datetime(2026, 6, 2, 12, 0, tzinfo=dt_timezone.utc),
            category='noticias',
            content_hash='hash-noticias-1',
        )
        self.pagamentos_article = NewsArticle.objects.create(
            island=self.island,
            source=self.joraa_source,
            title='JORAA payment',
            summary='Soma dos montantes: 100 €',
            link='https://jo.azores.gov.pt/#/ato/test-uuid',
            published_at=datetime(2026, 6, 2, 11, 0, tzinfo=dt_timezone.utc),
            category='pagamentos',
            content_hash='hash-pagamentos-1',
        )

    def test_list_articles(self):
        response = self.client.get('/api/v3/news/articles', **self.headers)
        self.assertEqual(response.status_code, 200)
        articles = response.json()['articles']
        self.assertEqual(len(articles), 2)

    def test_list_articles_filter_noticias(self):
        response = self.client.get('/api/v3/news/articles?category=noticias', **self.headers)
        self.assertEqual(response.status_code, 200)
        articles = response.json()['articles']
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]['title'], 'ALRA headline')
        self.assertEqual(articles[0]['category'], 'noticias')

    def test_list_articles_filter_pagamentos(self):
        response = self.client.get('/api/v3/news/articles?category=pagamentos', **self.headers)
        self.assertEqual(response.status_code, 200)
        articles = response.json()['articles']
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]['title'], 'JORAA payment')
        self.assertEqual(articles[0]['category'], 'pagamentos')

    def test_list_articles_filter_other_category_empty(self):
        response = self.client.get('/api/v3/news/articles?category=other', **self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['articles']), 0)

    def test_article_detail(self):
        response = self.client.get(
            f'/api/v3/news/articles/{self.noticias_article.id}',
            **self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['link'], 'http://base.alra.pt:82/4DACTION/w_pesquisa_registo/4/9280')
