"""Blog template views.

Server-rendered pages for the blog index, post detail, category/tag
archives, and author pages. All SEO meta tags and structured data are
injected via template context.
"""

from __future__ import annotations

from django.conf import settings
from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render

from blog.services import (
    get_categories_with_counts,
    get_post_by_slug,
    get_published_posts,
    get_related_posts,
)


POSTS_PER_PAGE = 12


def post_list(request: HttpRequest) -> HttpResponse:
    """Blog index with filtering, sorting, search, and pagination."""
    language = request.GET.get("lang", "")
    category_slug = request.GET.get("category", "")
    tag_slug = request.GET.get("tag", "")
    search = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "-published_at")

    posts = get_published_posts(
        language=language or None,
        category_slug=category_slug or None,
        tag_slug=tag_slug or None,
        search=search or None,
        sort=sort,
    )

    paginator = Paginator(posts, POSTS_PER_PAGE)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    categories = get_categories_with_counts()

    page_title = "Blog"
    if page_obj.number > 1:
        page_title = f"Blog - Page {page_obj.number}"

    return render(request, "blog/post_list.html", {
        "page_obj": page_obj,
        "categories": categories,
        "current_language": language,
        "current_category": category_slug,
        "current_tag": tag_slug,
        "current_search": search,
        "current_sort": sort,
        "page_title": page_title,
        "PROJECT_URL": settings.PROJECT_URL,
    })


def post_detail(request: HttpRequest, slug: str) -> HttpResponse:
    """Single blog post with full SEO metadata and structured data."""
    try:
        post = get_post_by_slug(slug)
    except Exception:
        raise Http404("Blog post not found.")

    related = get_related_posts(post, limit=3)
    translations = post.get_translations()

    return render(request, "blog/post_detail.html", {
        "post": post,
        "related_posts": related,
        "translations": translations,
        "page_title": post.effective_meta_title,
        "PROJECT_URL": settings.PROJECT_URL,
        "PROJECT_NAME": settings.PROJECT_NAME,
    })


def category_detail(request: HttpRequest, slug: str) -> HttpResponse:
    """Category archive page."""
    posts = get_published_posts(category_slug=slug)
    if not posts.exists():
        raise Http404("Category not found.")

    category = posts.first().category
    paginator = Paginator(posts, POSTS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    return render(request, "blog/category_detail.html", {
        "category": category,
        "page_obj": page_obj,
        "page_title": f"{category.name} - Blog",
        "PROJECT_URL": settings.PROJECT_URL,
    })


def tag_detail(request: HttpRequest, slug: str) -> HttpResponse:
    """Tag archive page (noindexed by default)."""
    posts = get_published_posts(tag_slug=slug)
    if not posts.exists():
        raise Http404("Tag not found.")

    from blog.models import Tag
    tag = Tag.objects.get(slug=slug)

    paginator = Paginator(posts, POSTS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    return render(request, "blog/tag_detail.html", {
        "tag": tag,
        "page_obj": page_obj,
        "page_title": f"#{tag.name} - Blog",
        "noindex": True,
        "PROJECT_URL": settings.PROJECT_URL,
    })


def author_detail(request: HttpRequest, username: str) -> HttpResponse:
    """Author archive page."""
    posts = get_published_posts(author_username=username)
    if not posts.exists():
        raise Http404("Author not found.")

    author = posts.first().author
    paginator = Paginator(posts, POSTS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    return render(request, "blog/author_detail.html", {
        "author": author,
        "page_obj": page_obj,
        "page_title": f"Posts by {author.get_full_name() or author.username}",
        "PROJECT_URL": settings.PROJECT_URL,
    })
