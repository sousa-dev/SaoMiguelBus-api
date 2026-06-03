"""News RSS poll and v3 API tests."""

from datetime import datetime, timezone as dt_timezone
from unittest.mock import MagicMock, patch

from django.test import TestCase
from rest_framework.test import APIClient

from news.azores_filter_terms import AZORES_FILTER_TERMS
from news.models import NewsArticle, NewsSource, NewsSourceKind
from news.services import USER_AGENT, poll_source
from news.tests.test_azores_adapter import ALRA_FIXTURE, JORAA_FIXTURE
from tenancy.services import get_or_create_default_island


def _entry(title: str, link: str, summary: str = '', **extra) -> dict:
    base = {
        'title': title,
        'link': link,
        'summary': summary,
        'published_parsed': (2026, 6, 3, 12, 0, 0, 0, 0, 0),
    }
    base.update(extra)
    return base


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

    def _national_source(self, **kwargs) -> NewsSource:
        defaults = {
            'island': self.island,
            'name': 'National filtered',
            'rss_url': 'https://example.com/national.xml',
            'language': 'pt',
            'kind': NewsSourceKind.NATIONAL_FILTERED,
            'filter_terms': AZORES_FILTER_TERMS,
            'max_items_per_poll': 0,
            'active': True,
        }
        defaults.update(kwargs)
        return NewsSource.objects.create(**defaults)

    @patch('news.services.feedparser.parse')
    def test_poll_source_passes_user_agent(self, mock_parse):
        mock_parse.return_value = MagicMock(entries=[])
        poll_source(self.source)
        mock_parse.assert_called_once_with(self.source.rss_url, agent=USER_AGENT)

    @patch('news.services.feedparser.parse')
    def test_national_filtered_creates_azores_skips_mainland(self, mock_parse):
        source = self._national_source()
        mock_parse.return_value = MagicMock(
            entries=[
                _entry('Governo em Lisboa', 'https://example.com/lisboa'),
                _entry('Erupção em São Jorge', 'https://example.com/sao-jorge'),
            ],
        )
        created, skipped = poll_source(source)
        self.assertEqual(created, 1)
        self.assertEqual(skipped, 1)
        article = NewsArticle.objects.get()
        self.assertEqual(article.title, 'Erupção em São Jorge')

    @patch('news.services.feedparser.parse')
    def test_national_filtered_accent_and_case_insensitive(self, mock_parse):
        source = self._national_source(filter_terms=['acores', 'sao miguel'])
        mock_parse.return_value = MagicMock(
            entries=[
                _entry('AÇORES em destaque', 'https://example.com/a1'),
                _entry('Tempestade', 'https://example.com/a2', summary='na ilha de açores'),
                _entry('Alerta', 'https://example.com/a3', summary='São Miguel amanhã'),
            ],
        )
        created, skipped = poll_source(source)
        self.assertEqual(created, 3)
        self.assertEqual(skipped, 0)

    @patch('news.services.feedparser.parse')
    def test_national_filtered_match_in_summary_only(self, mock_parse):
        source = self._national_source(filter_terms=['ponta delgada'])
        mock_parse.return_value = MagicMock(
            entries=[
                _entry('Câmara municipal', 'https://example.com/pd', summary='reunião em Ponta Delgada'),
            ],
        )
        created, skipped = poll_source(source)
        self.assertEqual(created, 1)
        self.assertEqual(skipped, 0)

    @patch('news.services.feedparser.parse')
    def test_national_filtered_cap_limits_created(self, mock_parse):
        source = self._national_source(max_items_per_poll=2)
        mock_parse.return_value = MagicMock(
            entries=[
                _entry('Notícia Açores 1', 'https://example.com/a1', summary='Açores'),
                _entry('Notícia Açores 2', 'https://example.com/a2', summary='São Miguel'),
                _entry('Notícia Açores 3', 'https://example.com/a3', summary='Terceira'),
                _entry('Notícia Açores 4', 'https://example.com/a4', summary='Faial'),
                _entry('Notícia Açores 5', 'https://example.com/a5', summary='Pico'),
            ],
        )
        created, skipped = poll_source(source)
        self.assertEqual(created, 2)
        self.assertEqual(skipped, 3)

    @patch('news.services.feedparser.parse')
    def test_generic_source_unlimited_when_cap_zero(self, mock_parse):
        mock_parse.return_value = MagicMock(
            entries=[
                _entry('One', 'https://example.com/1'),
                _entry('Two', 'https://example.com/2'),
                _entry('Three', 'https://example.com/3'),
            ],
        )
        created, skipped = poll_source(self.source)
        self.assertEqual(created, 3)
        self.assertEqual(skipped, 0)

    @patch('news.services.feedparser.parse')
    def test_national_filtered_empty_terms_skips_all(self, mock_parse):
        source = self._national_source(filter_terms=[])
        mock_parse.return_value = MagicMock(
            entries=[_entry('Açores', 'https://example.com/acores', summary='Açores')],
        )
        created, skipped = poll_source(source)
        self.assertEqual(created, 0)
        self.assertEqual(skipped, 1)

    @patch('news.services.feedparser.parse')
    def test_national_filtered_mixed_feed_realistic(self, mock_parse):
        source = self._national_source(max_items_per_poll=10)
        mock_parse.return_value = MagicMock(
            entries=[
                _entry('Homem detido no Almada Fórum', 'https://example.com/1'),
                _entry('Incêndio em Porto', 'https://example.com/2'),
                _entry('Metro de Lisboa', 'https://example.com/3'),
                _entry('Erupção em São Jorge preocupa autoridades', 'https://example.com/4'),
                _entry(
                    'Câmara de Ponta Delgada aprova orçamento',
                    'https://example.com/5',
                ),
            ],
        )
        created, skipped = poll_source(source)
        self.assertEqual(created, 2)
        self.assertEqual(skipped, 3)
        titles = set(NewsArticle.objects.values_list('title', flat=True))
        self.assertIn('Erupção em São Jorge preocupa autoridades', titles)
        self.assertIn('Câmara de Ponta Delgada aprova orçamento', titles)

    @patch('news.services.feedparser.parse')
    def test_rtp_pais_filtered_ingests_azores_headline(self, mock_parse):
        source = self._national_source(
            name='RTP Notícias (País)',
            rss_url='https://www.rtp.pt/noticias/rss/pais',
        )
        mock_parse.return_value = MagicMock(
            entries=[
                _entry('Greve Geral em Lisboa', 'https://rtp.pt/1'),
                _entry(
                    'Aeroporto de Ponta Delgada. Milhares aguardam voo',
                    'https://rtp.pt/2',
                ),
            ],
        )
        created, skipped = poll_source(source)
        self.assertEqual(created, 1)
        self.assertEqual(skipped, 1)
        self.assertEqual(
            NewsArticle.objects.get().title,
            'Aeroporto de Ponta Delgada. Milhares aguardam voo',
        )


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
