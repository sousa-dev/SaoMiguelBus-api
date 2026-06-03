"""News RSS sources and articles."""

from __future__ import annotations

from django.db import models

from tenancy.models import TenantScopedModel


class NewsSourceKind(models.TextChoices):
    GENERIC = 'generic', 'Generic RSS'
    AZORES_DIGEST = 'azores_digest', 'Açores.net daily digest'
    NATIONAL_FILTERED = 'national_filtered', 'National RSS, Azores-filtered'


class NewsSource(TenantScopedModel):
    name = models.CharField(max_length=120)
    rss_url = models.URLField(max_length=500)
    language = models.CharField(max_length=8, default='pt')
    active = models.BooleanField(default=True)
    kind = models.CharField(
        max_length=32,
        choices=NewsSourceKind.choices,
        default=NewsSourceKind.GENERIC,
    )
    default_category = models.CharField(max_length=64, blank=True, default='')
    filter_terms = models.JSONField(default=list, blank=True)
    max_items_per_poll = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['name']
        unique_together = [('island', 'rss_url')]

    def __str__(self) -> str:
        return self.name


class NewsArticle(TenantScopedModel):
    source = models.ForeignKey(NewsSource, on_delete=models.CASCADE, related_name='articles')
    title = models.CharField(max_length=500)
    summary = models.TextField(blank=True, default='')
    link = models.URLField(max_length=1000)
    published_at = models.DateTimeField(db_index=True)
    category = models.CharField(max_length=64, blank=True, default='')
    content_hash = models.CharField(max_length=64, db_index=True)

    class Meta:
        ordering = ['-published_at']
        unique_together = [('island', 'content_hash')]
        indexes = [
            models.Index(fields=['island', '-published_at']),
            models.Index(fields=['island', 'category']),
        ]

    def __str__(self) -> str:
        return self.title[:80]
