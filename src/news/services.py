"""News RSS ingestion and article queries."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone as dt_timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any

import feedparser
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from news.models import NewsArticle, NewsSource
from tenancy.models import Island
from tenancy.services import for_island

TAG_RE = re.compile(r'<[^>]+>')


def _strip_html(value: str) -> str:
    return unescape(TAG_RE.sub('', value or '')).strip()


def _entry_hash(source_id: int, link: str, title: str) -> str:
    payload = f'{source_id}:{link}:{title}'.encode()
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


def poll_source(source: NewsSource) -> tuple[int, int]:
    """Fetch RSS for one source. Returns (created, skipped)."""
    parsed = feedparser.parse(source.rss_url)
    created = 0
    skipped = 0

    for entry in parsed.entries:
        link = str(entry.get('link', '')).strip()
        title = _strip_html(str(entry.get('title', '')).strip())
        if not link or not title:
            skipped += 1
            continue

        summary_raw = entry.get('summary') or entry.get('description') or ''
        summary = _strip_html(str(summary_raw))[:2000]
        published_at = _parse_published(entry)
        category = _entry_category(entry)
        content_hash = _entry_hash(source.id, link, title)

        if NewsArticle.objects.filter(island=source.island, link=link).exists():
            skipped += 1
            continue
        if NewsArticle.objects.filter(island=source.island, content_hash=content_hash).exists():
            skipped += 1
            continue

        NewsArticle.objects.create(
            island=source.island,
            source=source,
            title=title,
            summary=summary,
            link=link,
            published_at=published_at,
            category=category,
            content_hash=content_hash,
        )
        created += 1

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


def list_articles(
    *,
    category: str = '',
    source_id: int | None = None,
    query: str = '',
    limit: int = 50,
) -> list[dict[str, Any]]:
    qs = NewsArticle.objects.select_related('source').order_by('-published_at')
    if category:
        qs = qs.filter(category__iexact=category)
    if source_id:
        qs = qs.filter(source_id=source_id)
    if query:
        qs = qs.filter(title__icontains=query)
    limit = max(1, min(limit, 100))
    return [serialize_article(a) for a in qs[:limit]]


def get_article(article_id: int) -> dict[str, Any] | None:
    try:
        article = NewsArticle.objects.select_related('source').get(id=article_id)
    except NewsArticle.DoesNotExist:
        return None
    return serialize_article(article)
