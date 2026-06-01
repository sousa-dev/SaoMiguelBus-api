"""Blog models.

SEO-optimized content models for a multi-language lead-generation blog.
Each post carries its own meta tags, structured data fields, and CTA
configuration. Translations are linked via ``translation_group`` UUID.
"""

from __future__ import annotations

import uuid
from typing import Optional

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


class Category(models.Model):
    """Blog post category with hierarchical support.

    Categories get their own archive pages and sitemap entries.
    """

    name = models.CharField(max_length=100, help_text="Display name.")
    slug = models.SlugField(max_length=120, unique=True, help_text="URL slug.")
    description = models.TextField(
        blank=True,
        help_text="SEO description for the category archive page (1-2 sentences).",
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
        help_text="Parent category for hierarchical organization.",
    )

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("blog:category_detail", kwargs={"slug": self.slug})


class Tag(models.Model):
    """Lightweight cross-cutting topic label.

    Keep to 3-5 tags per post. Tag archive pages are noindexed by default
    to avoid thin-content SEO penalties.
    """

    name = models.CharField(max_length=80, help_text="Display name.")
    slug = models.SlugField(max_length=100, unique=True, help_text="URL slug.")

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("blog:tag_detail", kwargs={"slug": self.slug})


class BlogPost(models.Model):
    """A single blog post optimised for SEO and lead generation.

    Attributes:
        title: Display title shown to readers.
        slug: URL-safe identifier, unique per language.
        body: Full post content (HTML).
        excerpt: Short summary for index cards and RSS feeds.
        meta_title: Override for ``<title>`` tag (50-70 chars).
        meta_description: Search engine snippet (150-160 chars).
        focus_keyword: Primary keyword target for internal scoring.
        featured_image / featured_image_alt: Hero image with alt text.
        og_image: Optional 1200x630 override for social sharing.
        category: Single primary category (ForeignKey).
        tags: Cross-cutting topic tags (ManyToMany).
        language: ISO 639-1 code (``en``, ``fr``, ``pt-BR``).
        translation_group: UUID linking all translations of the same post.
        cta_text / cta_url / lead_magnet_title: Per-post CTA configuration.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        SCHEDULED = "scheduled", "Scheduled"

    # -- Core content ---------------------------------------------------------
    title = models.CharField(max_length=250, help_text="Display title shown to readers.")
    slug = models.SlugField(
        max_length=280,
        help_text="URL-safe identifier. Should be unique per language.",
    )
    body = models.TextField(help_text="Full post content (HTML).")
    excerpt = models.TextField(
        max_length=500,
        blank=True,
        help_text="Short summary for blog index cards and RSS. "
        "Falls back to first 160 chars of body if empty.",
    )

    # -- SEO fields -----------------------------------------------------------
    meta_title = models.CharField(
        max_length=70,
        blank=True,
        help_text="Override for <title> tag. 50-70 chars. Defaults to title.",
    )
    meta_description = models.CharField(
        max_length=160,
        blank=True,
        help_text="Search engine snippet. 150-160 chars.",
    )
    focus_keyword = models.CharField(
        max_length=120,
        blank=True,
        help_text="Primary keyword to target (internal SEO scoring).",
    )
    canonical_url = models.URLField(
        blank=True,
        help_text="Override canonical URL for syndicated content.",
    )
    noindex = models.BooleanField(
        default=False,
        help_text="Add noindex meta tag to exclude from search engines.",
    )

    # -- Media ----------------------------------------------------------------
    featured_image = models.ImageField(
        upload_to="blog/featured/%Y/%m/",
        blank=True,
        null=True,
        help_text="Hero image displayed at the top of the post.",
    )
    featured_image_alt = models.CharField(
        max_length=125,
        blank=True,
        help_text="Descriptive alt text for the featured image.",
    )
    og_image = models.ImageField(
        upload_to="blog/og/%Y/%m/",
        blank=True,
        null=True,
        help_text="1200x630 image for social sharing. Falls back to featured_image.",
    )

    # -- Taxonomy -------------------------------------------------------------
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="posts",
        help_text="One primary category per post.",
    )
    tags = models.ManyToManyField(
        Tag,
        blank=True,
        related_name="posts",
        help_text="Cross-cutting topic tags. Use 3-5 per post.",
    )

    # -- Authorship -----------------------------------------------------------
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="blog_posts",
    )

    # -- Publishing -----------------------------------------------------------
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # -- Computed -------------------------------------------------------------
    word_count = models.PositiveIntegerField(default=0, editable=False)

    # -- Language & translations ----------------------------------------------
    language = models.CharField(
        max_length=7,
        default="en",
        db_index=True,
        help_text="ISO 639-1 code (en, fr, es, pt-BR).",
    )
    translation_group = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Shared UUID linking all translations of the same post.",
    )

    # -- Lead generation ------------------------------------------------------
    cta_text = models.CharField(
        max_length=200,
        blank=True,
        help_text="Primary CTA button text, e.g. 'Get the Free Checklist'.",
    )
    cta_url = models.URLField(
        blank=True,
        help_text="Where the CTA button links to.",
    )
    lead_magnet_title = models.CharField(
        max_length=200,
        blank=True,
        help_text="Name of the lead magnet offered in this post.",
    )

    class Meta:
        ordering = ["-published_at"]
        unique_together = [("slug", "language")]
        indexes = [
            models.Index(fields=["status", "published_at"]),
            models.Index(fields=["language", "status"]),
            models.Index(fields=["category", "status"]),
            models.Index(fields=["translation_group"]),
        ]

    def __str__(self) -> str:
        return f"[{self.language}] {self.title}"

    def save(self, *args: object, **kwargs: object) -> None:
        if not self.slug:
            self.slug = slugify(self.title)
        self.word_count = len(self.body.split())
        if self.status == self.Status.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("blog:post_detail", kwargs={"slug": self.slug})

    # -- Properties -----------------------------------------------------------

    @property
    def reading_time_minutes(self) -> int:
        """Estimated reading time at 238 wpm."""
        return max(1, round(self.word_count / 238))

    @property
    def effective_meta_title(self) -> str:
        return self.meta_title or self.title

    @property
    def effective_og_image(self) -> Optional[object]:
        return self.og_image or self.featured_image

    @property
    def effective_excerpt(self) -> str:
        if self.excerpt:
            return self.excerpt
        plain = self.body[:160]
        if " " in plain:
            plain = plain.rsplit(" ", 1)[0]
        return plain + "..."

    def get_translations(self) -> models.QuerySet:
        """Return published translations of this post (excluding self)."""
        if not self.translation_group:
            return BlogPost.objects.none()
        return BlogPost.objects.filter(
            translation_group=self.translation_group,
            status=self.Status.PUBLISHED,
        ).exclude(pk=self.pk)

    def assign_translation_group(self) -> None:
        """Assign a ``translation_group`` UUID if not already set."""
        if not self.translation_group:
            self.translation_group = uuid.uuid4()
            self.save(update_fields=["translation_group"])
