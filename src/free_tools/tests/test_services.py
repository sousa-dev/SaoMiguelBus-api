"""Tests for free_tools.services."""

from __future__ import annotations

import pytest
from django.utils import timezone

from free_tools.models import FreeTool, ToolCategory
from free_tools.services import (
    get_categories_with_counts,
    get_published_tools,
    get_tool_by_slug,
)


@pytest.fixture
def category(db: None) -> ToolCategory:
    """Tool category for fixtures."""
    return ToolCategory.objects.create(name="Generators", slug="generators")


def _create_tool(
    *,
    name: str,
    slug: str,
    category: ToolCategory | None = None,
    status: str = FreeTool.Status.PUBLISHED,
    language: str = "en",
    sort_order: int = 0,
    tagline: str = "",
) -> FreeTool:
    """Create a free tool with sensible defaults."""
    return FreeTool.objects.create(
        name=name,
        slug=slug,
        description=f"<p>{name} description</p>",
        template_name="free_tools/tools/example.html",
        status=status,
        language=language,
        category=category,
        sort_order=sort_order,
        tagline=tagline,
        published_at=timezone.now() if status == FreeTool.Status.PUBLISHED else None,
    )


@pytest.mark.django_db
def test_get_published_tools_returns_only_published(category: ToolCategory) -> None:
    """Happy path: only published tools are returned."""
    _create_tool(name="Live Tool", slug="live-tool", category=category)
    _create_tool(
        name="Draft Tool",
        slug="draft-tool",
        category=category,
        status=FreeTool.Status.DRAFT,
    )

    slugs = set(get_published_tools().values_list("slug", flat=True))

    assert "live-tool" in slugs
    assert "draft-tool" not in slugs


@pytest.mark.django_db
def test_get_published_tools_ordered(category: ToolCategory) -> None:
    """Happy path: tools ordered by sort_order then name."""
    _create_tool(name="Beta", slug="beta", category=category, sort_order=2)
    _create_tool(name="Alpha", slug="alpha", category=category, sort_order=1)

    slugs = [
        slug
        for slug in get_published_tools().values_list("slug", flat=True)
        if slug in {"alpha", "beta"}
    ]

    assert slugs == ["alpha", "beta"]


@pytest.mark.django_db
def test_get_published_tools_filters(category: ToolCategory) -> None:
    """Happy path: language, category, and search filters work."""
    other, _ = ToolCategory.objects.get_or_create(
        slug="security",
        defaults={"name": "Security"},
    )
    _create_tool(
        name="Key Generator",
        slug="key-gen",
        category=category,
        language="en",
        tagline="Generate Django secret keys",
    )
    _create_tool(
        name="French Tool",
        slug="fr-tool",
        category=category,
        language="fr",
    )
    _create_tool(name="Security Scan", slug="sec-scan", category=other)

    by_lang = set(get_published_tools(language="en").values_list("slug", flat=True))
    assert "key-gen" in by_lang
    assert "fr-tool" not in by_lang

    by_category = set(get_published_tools(category_slug="generators").values_list("slug", flat=True))
    assert {"key-gen", "fr-tool"}.issubset(by_category)

    by_search = set(get_published_tools(search="secret").values_list("slug", flat=True))
    assert "key-gen" in by_search


@pytest.mark.django_db
def test_get_tool_by_slug(category: ToolCategory) -> None:
    """Happy path: published slug resolves."""
    _create_tool(name="Published", slug="published-tool", category=category)

    tool = get_tool_by_slug("published-tool")

    assert tool.slug == "published-tool"


@pytest.mark.django_db
def test_get_tool_by_slug_draft_raises(category: ToolCategory) -> None:
    """Error path: draft tool slug raises DoesNotExist."""
    _create_tool(
        name="Draft",
        slug="draft-tool",
        category=category,
        status=FreeTool.Status.DRAFT,
    )

    with pytest.raises(FreeTool.DoesNotExist):
        get_tool_by_slug("draft-tool")


@pytest.mark.django_db
def test_get_tool_by_slug_missing_raises() -> None:
    """Error path: unknown slug raises DoesNotExist."""
    with pytest.raises(FreeTool.DoesNotExist):
        get_tool_by_slug("missing-tool")


@pytest.mark.django_db
def test_get_categories_with_counts(category: ToolCategory) -> None:
    """Happy path: only categories with published tools are returned."""
    empty = ToolCategory.objects.create(name="Empty", slug="empty")
    _create_tool(name="Counted", slug="counted", category=category)

    slugs = list(get_categories_with_counts().values_list("slug", flat=True))

    assert "generators" in slugs
    assert "empty" not in slugs
