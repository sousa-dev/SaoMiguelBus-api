"""Free tools template views."""

from __future__ import annotations

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.template.loader import get_template

from free_tools.services import (
    get_categories_with_counts,
    get_published_tools,
    get_tool_by_slug,
)


def tool_index(request: HttpRequest) -> HttpResponse:
    """Free tools directory / index page with search and category filter."""
    category_slug = request.GET.get("category", "")
    search = request.GET.get("q", "").strip()

    tools = get_published_tools(
        category_slug=category_slug or None,
        search=search or None,
    )
    categories = get_categories_with_counts()

    return render(request, "free_tools/tool_index.html", {
        "tools": tools,
        "categories": categories,
        "current_category": category_slug,
        "current_search": search,
        "page_title": "Free Tools",
        "PROJECT_URL": settings.PROJECT_URL,
        "PROJECT_NAME": settings.PROJECT_NAME,
    })


def tool_detail(request: HttpRequest, slug: str) -> HttpResponse:
    """Render a single free tool page with its interactive template."""
    try:
        tool = get_tool_by_slug(slug)
    except Exception:
        raise Http404("Tool not found.")

    try:
        get_template(tool.template_name)
    except Exception:
        raise Http404("Tool template not found.")

    translations = tool.get_translations()

    return render(request, "free_tools/tool_detail.html", {
        "tool": tool,
        "translations": translations,
        "page_title": tool.effective_meta_title,
        "PROJECT_URL": settings.PROJECT_URL,
        "PROJECT_NAME": settings.PROJECT_NAME,
    })


def category_detail(request: HttpRequest, slug: str) -> HttpResponse:
    """Category archive for free tools."""
    tools = get_published_tools(category_slug=slug)
    if not tools.exists():
        raise Http404("Category not found.")

    category = tools.first().category

    return render(request, "free_tools/category_detail.html", {
        "category": category,
        "tools": tools,
        "page_title": f"{category.name} Tools",
        "PROJECT_URL": settings.PROJECT_URL,
        "PROJECT_NAME": settings.PROJECT_NAME,
    })
