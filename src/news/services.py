"""News RSS ingestion and article queries."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timezone as dt_timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any

import feedparser
from django.db.models import F, Window
from django.db.models.functions import RowNumber
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from news.adapters.azores import parse_azores_digest
from news.models import NewsArticle, NewsSource, NewsSourceKind
from tenancy.models import Island
from tenancy.services import for_island

TAG_RE = re.compile(r'<[^>]+>')
SUMMARY_MAX_LEN = 2000
USER_AGENT = 'SaoMiguelBusBot/1.0 (+https://saomiguelbus.com)'
ARTICLES_PER_SOURCE_LIMIT = 25


def _strip_html(value: str) -> str:
    return unescape(TAG_RE.sub('', value or '')).strip()


def _fold(text: str) -> str:
    normalized = unicodedata.normalize('NFKD', text or '')
    stripped = ''.join(ch for ch in normalized if not unicodedata.combining(ch))
    return stripped.lower()


def _matches_terms(folded_text: str, terms: list[str] | None) -> bool:
    if not terms:
        return False
    for term in terms:
        folded_term = _fold(str(term))
        if folded_term and folded_term in folded_text:
            return True
    return False


def _entry_hash(source_id: int, link: str, title: str) -> str:
    payload = f'{source_id}:{link}:{title}'.encode()
    return hashlib.sha256(payload).hexdigest()


def _item_hash(source_id: int, link: str, summary: str) -> str:
    payload = f'{source_id}:{link}:{summary}'.encode()
    return hashlib.sha256(payload).hexdigest()


def _parse_published(entry: dict[str, Any]) -> datetime:
    for key in ('published_parsed', 'updated_parsed'):
        parsed = entry.get(key)
        if parsed:
            try:
                dt = datetime(*parsed[:6], tzinfo=dt_timezone.utc)
                return dt if timezone.is_aware(dt) else timezone.make_aware(dt)
            except (TypeError, ValueError):
                pass
    for key in ('published', 'updated'):
        raw = entry.get(key)
        if isinstance(raw, str):
            try:
                dt = parsedate_to_datetime(raw)
                return dt if timezone.is_aware(dt) else timezone.make_aware(dt)
            except (TypeError, ValueError):
                parsed = parse_datetime(raw)
                if parsed:
                    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)
    return timezone.now()


def _entry_category(entry: dict[str, Any]) -> str:
    tags = entry.get('tags') or []
    if tags:
        term = tags[0].get('term') if isinstance(tags[0], dict) else None
        if term:
            return str(term)[:64]
    return ''


def _format_item_summary(section: str, item_summary: str) -> str:
    if section:
        body = f'{section}\n\n{item_summary}'
    else:
        body = item_summary
    return body[:SUMMARY_MAX_LEN]


def _article_exists(island: Island, content_hash: str) -> bool:
    return NewsArticle.objects.filter(island=island, content_hash=content_hash).exists()


def _create_article(
    *,
    source: NewsSource,
    title: str,
    summary: str,
    link: str,
    published_at: datetime,
    category: str,
    content_hash: str,
) -> bool:
    if _article_exists(source.island, content_hash):
        return False

    NewsArticle.objects.create(
        island=source.island,
        source=source,
        title=title[:500],
        summary=summary,
        link=link,
        published_at=published_at,
        category=category,
        content_hash=content_hash,
    )
    return True


def _ingest_generic_entry(source: NewsSource, entry: dict[str, Any]) -> tuple[int, int]:
    link = str(entry.get('link', '')).strip()
    title = _strip_html(str(entry.get('title', '')).strip())
    if not link or not title:
        return 0, 1

    summary_raw = entry.get('summary') or entry.get('description') or ''
    summary = _strip_html(str(summary_raw))[:SUMMARY_MAX_LEN]
    published_at = _parse_published(entry)
    category = _entry_category(entry) or source.default_category
    content_hash = _entry_hash(source.id, link, title)

    if _create_article(
        source=source,
        title=title,
        summary=summary,
        link=link,
        published_at=published_at,
        category=category,
        content_hash=content_hash,
    ):
        return 1, 0
    return 0, 1


def _ingest_azores_digest_entry(source: NewsSource, entry: dict[str, Any]) -> tuple[int, int]:
    summary_raw = entry.get('summary') or entry.get('description') or ''
    items = parse_azores_digest(str(summary_raw))
    if not items:
        return _ingest_generic_entry(source, entry)

    published_at = _parse_published(entry)
    created = 0
    skipped = 0

    for item in items:
        title = item['title']
        link = item['link']
        item_summary = item['summary']
        summary = _format_item_summary(item.get('section', ''), item_summary)
        content_hash = _item_hash(source.id, link, item_summary)

        if _create_article(
            source=source,
            title=title,
            summary=summary,
            link=link,
            published_at=published_at,
            category=source.default_category,
            content_hash=content_hash,
        ):
            created += 1
        else:
            skipped += 1

    return created, skipped


def _ingest_national_filtered_entry(source: NewsSource, entry: dict[str, Any]) -> tuple[int, int]:
    link = str(entry.get('link', '')).strip()
    title = _strip_html(str(entry.get('title', '')).strip())
    if not link or not title:
        return 0, 1

    summary_raw = entry.get('summary') or entry.get('description') or ''
    summary = _strip_html(str(summary_raw))
    haystack = _fold(f'{title} {summary}')
    if not _matches_terms(haystack, source.filter_terms):
        return 0, 1

    return _ingest_generic_entry(source, entry)


def poll_source(source: NewsSource) -> tuple[int, int]:
    """Fetch RSS for one source. Returns (created, skipped)."""
    parsed = feedparser.parse(source.rss_url, agent=USER_AGENT)
    created = 0
    skipped = 0
    cap = source.max_items_per_poll

    for entry in parsed.entries:
        if cap > 0 and created >= cap:
            skipped += 1
            continue

        if source.kind == NewsSourceKind.AZORES_DIGEST:
            entry_created, entry_skipped = _ingest_azores_digest_entry(source, entry)
        elif source.kind == NewsSourceKind.NATIONAL_FILTERED:
            entry_created, entry_skipped = _ingest_national_filtered_entry(source, entry)
        else:
            entry_created, entry_skipped = _ingest_generic_entry(source, entry)

        created += entry_created
        skipped += entry_skipped

    return created, skipped


def poll_all_sources(*, island_key: str | None = None) -> dict[str, int]:
    """Poll active RSS sources. Returns aggregate counts."""
    if island_key:
        islands = Island.objects.filter(key=island_key)
    else:
        islands = Island.objects.filter(is_live=True)

    totals = {'sources': 0, 'created': 0, 'skipped': 0}
    for island in islands:
        with for_island(island):
            for source in NewsSource.objects.filter(active=True):
                totals['sources'] += 1
                created, skipped = poll_source(source)
                totals['created'] += created
                totals['skipped'] += skipped
    return totals


def serialize_article(article: NewsArticle) -> dict[str, Any]:
    return {
        'id': article.id,
        'title': article.title,
        'summary': article.summary,
        'link': article.link,
        'publishedAt': article.published_at.isoformat(),
        'category': article.category,
        'source': {
            'id': article.source_id,
            'name': article.source.name,
            'language': article.source.language,
        },
    }


def _articles_queryset(
    *,
    category: str = '',
    source_id: int | None = None,
    query: str = '',
):
    qs = NewsArticle.objects.select_related('source')
    if category:
        qs = qs.filter(category__iexact=category)
    if source_id:
        qs = qs.filter(source_id=source_id)
    if query:
        qs = qs.filter(title__icontains=query)
    return qs


def list_articles(
    *,
    category: str = '',
    source_id: int | None = None,
    query: str = '',
    limit: int = 50,
) -> list[dict[str, Any]]:
    per_source = ARTICLES_PER_SOURCE_LIMIT
    qs = _articles_queryset(category=category, source_id=source_id, query=query)

    if source_id:
        take = per_source
        if limit > 0:
            take = min(per_source, max(1, limit))
        articles = list(qs.order_by('-published_at')[:take])
    else:
        articles = list(
            qs.annotate(
                source_rank=Window(
                    expression=RowNumber(),
                    partition_by=[F('source_id')],
                    order_by=F('published_at').desc(),
                ),
            )
            .filter(source_rank__lte=per_source)
            .order_by('-published_at')
        )

    return [serialize_article(a) for a in articles]


def get_article(article_id: int) -> dict[str, Any] | None:
    try:
        article = NewsArticle.objects.select_related('source').get(id=article_id)
    except NewsArticle.DoesNotExist:
        return None
    return serialize_article(article)
