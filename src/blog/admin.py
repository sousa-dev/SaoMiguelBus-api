"""Blog admin configuration.

Rich admin UI for managing posts, categories, and tags with inline
SEO field previews and bulk actions.
"""

from __future__ import annotations

from django.contrib import admin
from django.utils.html import format_html

from .models import BlogPost, Category, Tag


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "parent", "post_count"]
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name"]

    def post_count(self, obj: Category) -> int:
        return obj.posts.filter(status=BlogPost.Status.PUBLISHED).count()

    post_count.short_description = "Published posts"


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name"]


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "language",
        "category",
        "status",
        "author",
        "published_at",
        "reading_time_display",
        "seo_status",
    ]
    list_filter = ["status", "language", "category", "tags"]
    search_fields = ["title", "body", "meta_title", "meta_description"]
    prepopulated_fields = {"slug": ("title",)}
    autocomplete_fields = ["category", "author"]
    filter_horizontal = ["tags"]
    readonly_fields = ["word_count", "created_at", "updated_at"]
    date_hierarchy = "published_at"

    fieldsets = [
        (None, {
            "fields": ("title", "slug", "body", "excerpt", "status"),
        }),
        ("SEO", {
            "fields": (
                "meta_title", "meta_description", "focus_keyword",
                "canonical_url", "noindex",
            ),
            "classes": ("collapse",),
        }),
        ("Media", {
            "fields": ("featured_image", "featured_image_alt", "og_image"),
        }),
        ("Taxonomy", {
            "fields": ("category", "tags"),
        }),
        ("Authorship & Language", {
            "fields": ("author", "language", "translation_group"),
        }),
        ("Lead Generation", {
            "fields": ("cta_text", "cta_url", "lead_magnet_title"),
            "classes": ("collapse",),
        }),
        ("Metadata", {
            "fields": ("published_at", "word_count", "created_at", "updated_at"),
        }),
    ]

    def reading_time_display(self, obj: BlogPost) -> str:
        return f"{obj.reading_time_minutes} min"

    reading_time_display.short_description = "Read time"

    def seo_status(self, obj: BlogPost) -> str:
        issues: list[str] = []
        if not obj.meta_title:
            issues.append("No meta title")
        elif len(obj.meta_title) > 70:
            issues.append("Meta title too long")
        if not obj.meta_description:
            issues.append("No meta desc")
        elif len(obj.meta_description) > 160:
            issues.append("Meta desc too long")
        if not obj.featured_image:
            issues.append("No image")
        if not obj.focus_keyword:
            issues.append("No keyword")

        if not issues:
            return format_html('<span style="color:green;">✓ Good</span>')
        return format_html(
            '<span style="color:orange;" title="{}">{} issue{}</span>',
            "; ".join(issues),
            len(issues),
            "s" if len(issues) > 1 else "",
        )

    seo_status.short_description = "SEO"
