"""Free tools service layer."""

from __future__ import annotations

from django.db.models import Count, Q, QuerySet

from free_tools.models import FreeTool, ToolCategory


def get_published_tools(
    *,
    language: str | None = None,
    category_slug: str | None = None,
    search: str | None = None,
) -> QuerySet[FreeTool]:
    """Return published tools with optional filters.

    Args:
        language: Filter by ISO 639-1 language code.
        category_slug: Filter by category slug.
        search: Search across name, tagline, description.
    """
    qs = (
        FreeTool.objects
        .filter(status=FreeTool.Status.PUBLISHED)
        .select_related("category")
    )
    if language:
        qs = qs.filter(language=language)
    if category_slug:
        qs = qs.filter(category__slug=category_slug)
    if search:
        qs = qs.filter(
            Q(name__icontains=search)
            | Q(tagline__icontains=search)
            | Q(description__icontains=search)
        )
    return qs.order_by("sort_order", "name")


def get_tool_by_slug(slug: str) -> FreeTool:
    """Retrieve a single published tool by slug.

    Raises:
        FreeTool.DoesNotExist: If not found.
    """
    return (
        FreeTool.objects
        .filter(slug=slug, status=FreeTool.Status.PUBLISHED)
        .select_related("category")
        .get()
    )


def get_categories_with_counts() -> QuerySet[ToolCategory]:
    """Return categories that have at least one published tool."""
    return ToolCategory.objects.annotate(
        tool_count=Count(
            "tools",
            filter=Q(tools__status=FreeTool.Status.PUBLISHED),
        ),
    ).filter(tool_count__gt=0).order_by("name")
