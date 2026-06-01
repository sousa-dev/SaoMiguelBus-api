"""Tests for blog.services."""

from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from blog.models import BlogPost, Category, Tag
from blog.services import (
    CreatePostInput,
    create_post,
    get_available_languages,
    get_categories_with_counts,
    get_post_by_slug,
    get_published_posts,
    get_related_posts,
    slugify_safe,
    update_post,
)


@pytest.fixture
def author(db: None) -> User:
    """Blog author for post fixtures."""
    return User.objects.create_user(username="author", password="testpass123")


@pytest.fixture
def category(db: None) -> Category:
    """Primary category for blog posts."""
    return Category.objects.create(name="SaaS", slug="saas")


@pytest.fixture
def tag(db: None) -> Tag:
    """Tag for blog posts."""
    return Tag.objects.create(name="Growth", slug="growth")


def _create_post(
    *,
    title: str,
    slug: str,
    status: str = BlogPost.Status.PUBLISHED,
    language: str = "en",
    category: Category | None = None,
    tags: list[Tag] | None = None,
    author: User | None = None,
    body: str = "<p>Body content here.</p>",
) -> BlogPost:
    """Create a blog post with sensible defaults."""
    post = BlogPost.objects.create(
        title=title,
        slug=slug,
        body=body,
        status=status,
        language=language,
        category=category,
        author=author,
        published_at=timezone.now() if status == BlogPost.Status.PUBLISHED else None,
    )
    if tags:
        post.tags.set(tags)
    return post


@pytest.mark.django_db
def test_get_published_posts_returns_only_published(
    category: Category,
) -> None:
    """Happy path: only published posts are returned."""
    _create_post(title="Live", slug="live", category=category)
    _create_post(title="Draft", slug="draft", status=BlogPost.Status.DRAFT)

    slugs = set(get_published_posts().values_list("slug", flat=True))

    assert "live" in slugs
    assert "draft" not in slugs


@pytest.mark.django_db
def test_get_published_posts_filters(
    category: Category,
    tag: Tag,
    author: User,
) -> None:
    """Happy path: language, category, tag, search, and sort filters work."""
    _create_post(
        title="English SaaS Guide",
        slug="en-guide",
        language="en",
        category=category,
        tags=[tag],
        author=author,
        body="<p>SaaS growth metrics explained.</p>",
    )
    _create_post(title="French Post", slug="fr-post", language="fr")

    by_lang = set(get_published_posts(language="en").values_list("slug", flat=True))
    assert "en-guide" in by_lang
    assert "fr-post" not in by_lang

    by_category = set(get_published_posts(category_slug="saas").values_list("slug", flat=True))
    assert "en-guide" in by_category

    by_tag = set(get_published_posts(tag_slug="growth").values_list("slug", flat=True))
    assert "en-guide" in by_tag

    by_author = set(get_published_posts(author_username="author").values_list("slug", flat=True))
    assert "en-guide" in by_author

    by_search = list(get_published_posts(search="metrics").values_list("slug", flat=True))
    assert by_search == ["en-guide"]

    by_sort = set(get_published_posts(sort="title").values_list("slug", flat=True))
    assert "en-guide" in by_sort


@pytest.mark.django_db
def test_get_published_posts_invalid_sort_falls_back(category: Category) -> None:
    """Edge case: invalid sort value falls back to -published_at."""
    _create_post(title="First", slug="first", category=category)
    _create_post(title="Second", slug="second", category=category)

    qs = get_published_posts(sort="not-a-real-field")
    assert set(qs.values_list("slug", flat=True)) >= {"first", "second"}


@pytest.mark.django_db
def test_get_post_by_slug(category: Category) -> None:
    """Happy path: published slug resolves; draft slug raises DoesNotExist."""
    _create_post(title="Published", slug="published", category=category)
    _create_post(
        title="Draft Only",
        slug="draft-only",
        status=BlogPost.Status.DRAFT,
        category=category,
    )

    post = get_post_by_slug("published")
    assert post.slug == "published"

    with pytest.raises(BlogPost.DoesNotExist):
        get_post_by_slug("draft-only")


@pytest.mark.django_db
def test_get_related_posts_by_category(category: Category) -> None:
    """Happy path: related posts share category and exclude self."""
    source = _create_post(title="Source", slug="source", category=category)
    _create_post(title="Related", slug="related", category=category)
    _create_post(title="Other", slug="other")

    related = list(get_related_posts(source).values_list("slug", flat=True))

    assert related == ["related"]


@pytest.mark.django_db
def test_get_related_posts_by_tags(tag: Tag) -> None:
    """Edge case: posts with tags but no category match by tag."""
    source = _create_post(title="Tagged Source", slug="tagged-source", tags=[tag])
    _create_post(title="Tagged Related", slug="tagged-related", tags=[tag])

    related = list(get_related_posts(source).values_list("slug", flat=True))

    assert related == ["tagged-related"]


@pytest.mark.django_db
def test_get_categories_with_counts(category: Category) -> None:
    """Happy path: categories with published posts are included."""
    empty = Category.objects.create(name="Empty", slug="empty")
    _create_post(title="Counted", slug="counted", category=category)

    slugs = list(get_categories_with_counts().values_list("slug", flat=True))

    assert "saas" in slugs
    assert "empty" not in slugs


@pytest.mark.django_db
def test_get_available_languages(category: Category) -> None:
    """Happy path: language codes include published post counts."""
    _create_post(title="English One", slug="en-one", language="en", category=category)
    _create_post(title="English Two", slug="en-two", language="en", category=category)
    _create_post(title="French One", slug="fr-one", language="fr")

    languages = dict(get_available_languages())

    assert languages["en"] >= 2
    assert languages["fr"] >= 1


@pytest.mark.django_db
def test_create_post_sets_slug_tags_and_translation_group(
    category: Category,
    tag: Tag,
    author: User,
) -> None:
    """Happy path: create_post builds slug, tags, and translation group."""
    data = CreatePostInput(
        title="Hello World",
        body="<p>Content</p>",
        category_slug="saas",
        tag_slugs=["growth"],
        author_id=author.id,
        status="published",
    )

    post = create_post(data)

    assert post.slug == "hello-world"
    assert post.category == category
    assert list(post.tags.values_list("slug", flat=True)) == ["growth"]
    assert post.translation_group is not None


@pytest.mark.django_db
def test_create_post_links_translation_group(category: Category) -> None:
    """Happy path: translation_of_slug links to source translation group."""
    source = _create_post(title="Source Post", slug="source-post", category=category)
    assert source.translation_group is None

    translation = create_post(
        CreatePostInput(
            title="Traduction",
            body="<p>FR</p>",
            language="fr",
            translation_of_slug="source-post",
            status="published",
        )
    )

    source.refresh_from_db()
    assert source.translation_group is not None
    assert translation.translation_group == source.translation_group


@pytest.mark.django_db
def test_update_post_changes_fields_and_tags(
    category: Category,
    tag: Tag,
) -> None:
    """Happy path: update_post mutates fields and tag slugs."""
    post = _create_post(title="Original", slug="original", category=category)

    updated = update_post(
        "original",
        title="Updated Title",
        tag_slugs=["growth"],
        category_slug="saas",
    )

    assert updated.title == "Updated Title"
    assert list(updated.tags.values_list("slug", flat=True)) == ["growth"]
    assert updated.category == category


@pytest.mark.django_db
def test_slugify_safe_appends_suffix_when_taken(category: Category) -> None:
    """Edge case: duplicate slug gets a unique suffix."""
    _create_post(title="Taken Title", slug="taken-title", category=category)

    slug = slugify_safe("Taken Title")

    assert slug.startswith("taken-title-")
    assert slug != "taken-title"


@pytest.mark.django_db
def test_create_post_unknown_translation_gets_new_group() -> None:
    """Edge case: missing translation source gets a fresh translation_group."""
    post = create_post(
        CreatePostInput(
            title="Orphan Translation",
            body="<p>x</p>",
            translation_of_slug="does-not-exist",
        )
    )

    assert post.translation_group is not None
    assert isinstance(post.translation_group, uuid.UUID)
