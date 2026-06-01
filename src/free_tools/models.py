"""Free tools models.

Each ``FreeTool`` represents a single free utility page (e.g. a secret
key generator, a password checker, a JSON formatter). The model stores
all SEO metadata, CTA configuration, and references the Django template
that implements the tool's interactive UI.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


class ToolCategory(models.Model):
    """Grouping for free tools (e.g. "Security", "Formatters", "Generators")."""

    name = models.CharField(max_length=100, help_text="Display name.")
    slug = models.SlugField(max_length=120, unique=True, help_text="URL slug.")
    description = models.TextField(
        blank=True,
        help_text="SEO description for the category page.",
    )
    icon_class = models.CharField(
        max_length=60,
        blank=True,
        help_text="Font Awesome class, e.g. 'fas fa-shield-alt'.",
    )

    class Meta:
        verbose_name_plural = "tool categories"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("free_tools:category_detail", kwargs={"slug": self.slug})


class FreeTool(models.Model):
    """A single free tool page optimised for SEO and lead generation.

    Each tool has:
    - A Django template (``template_name``) that renders the interactive UI.
    - Full SEO metadata (meta_title, meta_description, JSON-LD fields).
    - CTA configuration for lead capture.
    - Multi-language support via ``translation_group``.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    # -- Identity -------------------------------------------------------------
    name = models.CharField(max_length=200, help_text="Tool display name.")
    slug = models.SlugField(max_length=220, help_text="URL slug, unique per language.")
    tagline = models.CharField(
        max_length=300,
        blank=True,
        help_text="One-line description shown below the title.",
    )
    description = models.TextField(
        help_text="Detailed description (HTML). Rendered below the tool UI for SEO depth.",
    )
    template_name = models.CharField(
        max_length=200,
        help_text="Path to the Django template implementing this tool's UI, "
        "e.g. 'free_tools/tools/secret_key_generator.html'.",
    )

    # -- SEO ------------------------------------------------------------------
    meta_title = models.CharField(
        max_length=70, blank=True,
        help_text="Override <title> tag. 50-70 chars. Defaults to name.",
    )
    meta_description = models.CharField(
        max_length=160, blank=True,
        help_text="Search engine snippet. 150-160 chars.",
    )
    focus_keyword = models.CharField(
        max_length=120, blank=True,
        help_text="Primary keyword to target.",
    )
    canonical_url = models.URLField(
        blank=True,
        help_text="Override canonical URL if syndicated.",
    )
    noindex = models.BooleanField(default=False)

    # -- Media ----------------------------------------------------------------
    og_image = models.ImageField(
        upload_to="free_tools/og/%Y/%m/",
        blank=True, null=True,
        help_text="1200x630 social sharing image.",
    )
    icon_class = models.CharField(
        max_length=60,
        blank=True,
        help_text="Font Awesome icon class for the tool card.",
    )

    # -- Taxonomy -------------------------------------------------------------
    category = models.ForeignKey(
        ToolCategory,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="tools",
    )

    # -- Publishing -----------------------------------------------------------
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True,
    )
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sort_order = models.IntegerField(
        default=0,
        help_text="Lower numbers appear first on the index page.",
    )

    # -- Language & translations ----------------------------------------------
    language = models.CharField(max_length=7, default="en", db_index=True)
    translation_group = models.UUIDField(
        null=True, blank=True, db_index=True,
        help_text="UUID linking translations of the same tool.",
    )

    # -- Lead generation ------------------------------------------------------
    cta_text = models.CharField(max_length=200, blank=True)
    cta_url = models.URLField(blank=True)
    lead_magnet_title = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["sort_order", "name"]
        unique_together = [("slug", "language")]
        indexes = [
            models.Index(fields=["status", "sort_order"]),
            models.Index(fields=["language", "status"]),
            models.Index(fields=["category", "status"]),
            models.Index(fields=["translation_group"]),
        ]

    def __str__(self) -> str:
        return f"[{self.language}] {self.name}"

    def save(self, *args: object, **kwargs: object) -> None:
        if not self.slug:
            self.slug = slugify(self.name)
        if self.status == self.Status.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        if not self.translation_group:
            self.translation_group = uuid.uuid4()
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("free_tools:tool_detail", kwargs={"slug": self.slug})

    @property
    def effective_meta_title(self) -> str:
        return self.meta_title or self.name

    def get_translations(self) -> models.QuerySet:
        if not self.translation_group:
            return FreeTool.objects.none()
        return FreeTool.objects.filter(
            translation_group=self.translation_group,
            status=self.Status.PUBLISHED,
        ).exclude(pk=self.pk)
