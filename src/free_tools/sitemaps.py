"""Free tools sitemap classes."""

from __future__ import annotations

from django.contrib.sitemaps import Sitemap

from free_tools.models import FreeTool, ToolCategory


class FreeToolSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.8
    protocol = "https"

    def items(self):
        return FreeTool.objects.filter(
            status=FreeTool.Status.PUBLISHED,
        ).order_by("sort_order")

    def lastmod(self, obj: FreeTool):
        return obj.updated_at

    def location(self, obj: FreeTool) -> str:
        return obj.get_absolute_url()


class ToolCategorySitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.6
    protocol = "https"

    def items(self):
        return ToolCategory.objects.filter(
            tools__status=FreeTool.Status.PUBLISHED,
        ).distinct()

    def lastmod(self, obj: ToolCategory):
        latest = obj.tools.filter(
            status=FreeTool.Status.PUBLISHED,
        ).order_by("-updated_at").first()
        return latest.updated_at if latest else None

    def location(self, obj: ToolCategory) -> str:
        return obj.get_absolute_url()
