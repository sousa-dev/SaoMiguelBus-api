"""Blog service layer.

All blog business logic — querying, filtering, creating, and updating
posts — lives here. Views and API endpoints delegate to these functions.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Optional

from django.contrib.auth.models import User
from django.db.models import Q, QuerySet
from django.utils import timezone

from blog.models import BlogPost, Category, Tag


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


def get_published_posts(
    *,
    language: str | None = None,
    category_slug: str | None = None,
    tag_slug: str | None = None,
    author_username: str | None = None,
    search: str | None = None,
    sort: str = "-published_at",
) -> QuerySet[BlogPost]:
    """Return published posts with optional filters and sorting.

    Args:
        language: Filter by ISO 639-1 language code.
        category_slug: Filter by category slug.
        tag_slug: Filter by tag slug.
        author_username: Filter by author username.
        search: Full-text search across title, body, excerpt.
        sort: Order-by field. Prefix with ``-`` for descending.
            Allowed: ``published_at``, ``-published_at``, ``title``,
            ``-title``, ``word_count``, ``-word_count``.

    Returns:
        A filtered, sorted queryset of published ``BlogPost`` instances.
    """
    ALLOWED_SORTS = {
        "published_at", "-published_at",
        "title", "-title",
        "word_count", "-word_count",
        "updated_at", "-updated_at",
    }
    if sort not in ALLOWED_SORTS:
        sort = "-published_at"

    qs = (
        BlogPost.objects
        .filter(status=BlogPost.Status.PUBLISHED)
        .select_related("author", "category")
        .prefetch_related("tags")
    )

    if language:
        qs = qs.filter(language=language)
    if category_slug:
        qs = qs.filter(category__slug=category_slug)
    if tag_slug:
        qs = qs.filter(tags__slug=tag_slug)
    if author_username:
        qs = qs.filter(author__username=author_username)
    if search:
        qs = qs.filter(
            Q(title__icontains=search)
            | Q(body__icontains=search)
            | Q(excerpt__icontains=search)
            | Q(meta_description__icontains=search)
        )

    return qs.order_by(sort)


def get_post_by_slug(slug: str) -> BlogPost:
    """Retrieve a single published post by slug.

    Raises:
        BlogPost.DoesNotExist: If no matching published post exists.
    """
    return (
        BlogPost.objects
        .filter(slug=slug, status=BlogPost.Status.PUBLISHED)
        .select_related("author", "category")
        .prefetch_related("tags")
        .get()
    )


def get_related_posts(post: BlogPost, limit: int = 3) -> QuerySet[BlogPost]:
    """Return related published posts based on category and tags."""
    qs = (
        BlogPost.objects
        .filter(status=BlogPost.Status.PUBLISHED)
        .exclude(pk=post.pk)
        .select_related("category")
    )
    if post.category:
        qs = qs.filter(category=post.category)
    elif post.tags.exists():
        qs = qs.filter(tags__in=post.tags.all()).distinct()
    return qs[:limit]


def get_categories_with_counts() -> QuerySet[Category]:
    """Return categories annotated with their published post count."""
    from django.db.models import Count

    return Category.objects.annotate(
        post_count=Count(
            "posts",
            filter=Q(posts__status=BlogPost.Status.PUBLISHED),
        )
    ).filter(post_count__gt=0).order_by("name")


def get_available_languages() -> list[tuple[str, int]]:
    """Return language codes with their published post counts."""
    return list(
        BlogPost.objects
        .filter(status=BlogPost.Status.PUBLISHED)
        .values_list("language")
        .annotate(count=models.Count("id"))
        .order_by("language")
    )


# ---------------------------------------------------------------------------
# Write operations (for API and admin)
# ---------------------------------------------------------------------------


@dataclass
class CreatePostInput:
    """Input for creating a new blog post."""

    title: str
    body: str
    language: str = "en"
    slug: str = ""
    excerpt: str = ""
    meta_title: str = ""
    meta_description: str = ""
    focus_keyword: str = ""
    category_slug: str = ""
    tag_slugs: list[str] | None = None
    author_id: int | None = None
    status: str = "draft"
    featured_image_alt: str = ""
    cta_text: str = ""
    cta_url: str = ""
    lead_magnet_title: str = ""
    translation_of_slug: str = ""


def create_post(data: CreatePostInput) -> BlogPost:
    """Create a new blog post from structured input.

    If ``translation_of_slug`` is provided, the new post is linked to the
    same ``translation_group`` as the referenced post.

    Args:
        data: Validated input fields.

    Returns:
        The newly created ``BlogPost``.
    """
    post = BlogPost(
        title=data.title,
        slug=data.slug or slugify_safe(data.title),
        body=data.body,
        excerpt=data.excerpt,
        language=data.language,
        meta_title=data.meta_title,
        meta_description=data.meta_description,
        focus_keyword=data.focus_keyword,
        featured_image_alt=data.featured_image_alt,
        cta_text=data.cta_text,
        cta_url=data.cta_url,
        lead_magnet_title=data.lead_magnet_title,
    )

    if data.status in dict(BlogPost.Status.choices):
        post.status = data.status

    if data.author_id:
        post.author_id = data.author_id

    if data.category_slug:
        post.category = Category.objects.filter(slug=data.category_slug).first()

    if data.translation_of_slug:
        source = BlogPost.objects.filter(slug=data.translation_of_slug).first()
        if source:
            if not source.translation_group:
                source.translation_group = uuid.uuid4()
                source.save(update_fields=["translation_group"])
            post.translation_group = source.translation_group
        else:
            post.translation_group = uuid.uuid4()
    else:
        post.translation_group = uuid.uuid4()

    post.save()

    if data.tag_slugs:
        tags = Tag.objects.filter(slug__in=data.tag_slugs)
        post.tags.set(tags)

    return post


def update_post(slug: str, **fields: Any) -> BlogPost:
    """Update an existing post by slug.

    Args:
        slug: The post slug to update.
        **fields: Keyword arguments matching ``BlogPost`` field names.

    Returns:
        The updated ``BlogPost``.

    Raises:
        BlogPost.DoesNotExist: If no post with that slug exists.
    """
    post = BlogPost.objects.get(slug=slug)
    tag_slugs = fields.pop("tag_slugs", None)
    category_slug = fields.pop("category_slug", None)

    for field_name, value in fields.items():
        if hasattr(post, field_name):
            setattr(post, field_name, value)

    if category_slug is not None:
        post.category = Category.objects.filter(slug=category_slug).first()

    post.save()

    if tag_slugs is not None:
        tags = Tag.objects.filter(slug__in=tag_slugs)
        post.tags.set(tags)

    return post


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

from django.db import models  # noqa: E402
from django.utils.text import slugify  # noqa: E402


def slugify_safe(title: str) -> str:
    """Generate a slug, appending a short suffix if the base slug is taken."""
    base = slugify(title)
    if not BlogPost.objects.filter(slug=base).exists():
        return base
    return f"{base}-{uuid.uuid4().hex[:6]}"
