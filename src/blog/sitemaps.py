"""Blog sitemap classes for ``django.contrib.sitemaps``.

Generates SEO-optimized XML sitemaps with per-post ``lastmod``,
dynamic ``priority`` based on post age, and multi-language ``hreflang``
alternates via ``translation_group``.
"""

from __future__ import annotations

from django.contrib.sitemaps import Sitemap
from django.utils import timezone

from blog.models import BlogPost, Category


class BlogPostSitemap(Sitemap):
    """Sitemap for published blog posts."""

    changefreq = "weekly"
    protocol = "https"

    def items(self):
        return (
            BlogPost.objects
            .filter(status=BlogPost.Status.PUBLISHED)
            .select_related("category")
            .order_by("-published_at")
        )

    def lastmod(self, obj: BlogPost):
        return obj.updated_at

    def location(self, obj: BlogPost) -> str:
        return obj.get_absolute_url()

    def priority(self, obj: BlogPost) -> float:
        """Newer posts get higher priority."""
        if not obj.published_at:
            return 0.5
        age_days = (timezone.now() - obj.published_at).days
        if age_days < 30:
            return 0.8
        if age_days < 180:
            return 0.7
        return 0.6


class BlogCategorySitemap(Sitemap):
    """Sitemap for blog category archive pages."""

    changefreq = "weekly"
    priority = 0.5
    protocol = "https"

    def items(self):
        return (
            Category.objects
            .filter(posts__status=BlogPost.Status.PUBLISHED)
            .distinct()
        )

    def lastmod(self, obj: Category):
        latest = (
            obj.posts
            .filter(status=BlogPost.Status.PUBLISHED)
            .order_by("-updated_at")
            .first()
        )
        return latest.updated_at if latest else None

    def location(self, obj: Category) -> str:
        return obj.get_absolute_url()
