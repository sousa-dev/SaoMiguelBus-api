"""Free tools admin configuration."""

from __future__ import annotations

from django.contrib import admin
from django.utils.html import format_html

from .models import FreeTool, ToolCategory


@admin.register(ToolCategory)
class ToolCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "icon_class"]
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name"]


@admin.register(FreeTool)
class FreeToolAdmin(admin.ModelAdmin):
    list_display = [
        "name", "language", "category", "status",
        "sort_order", "published_at", "seo_check",
    ]
    list_filter = ["status", "language", "category"]
    list_editable = ["sort_order"]
    search_fields = ["name", "description", "meta_title"]
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ["category"]

    fieldsets = [
        (None, {
            "fields": ("name", "slug", "tagline", "description", "template_name", "status"),
        }),
        ("SEO", {
            "fields": (
                "meta_title", "meta_description", "focus_keyword",
                "canonical_url", "noindex",
            ),
            "classes": ("collapse",),
        }),
        ("Media & Display", {
            "fields": ("og_image", "icon_class", "sort_order"),
        }),
        ("Taxonomy & Language", {
            "fields": ("category", "language", "translation_group"),
        }),
        ("Lead Generation", {
            "fields": ("cta_text", "cta_url", "lead_magnet_title"),
            "classes": ("collapse",),
        }),
        ("Metadata", {
            "fields": ("published_at", "created_at", "updated_at"),
        }),
    ]
    readonly_fields = ["created_at", "updated_at"]

    def seo_check(self, obj: FreeTool) -> str:
        issues: list[str] = []
        if not obj.meta_title:
            issues.append("No meta title")
        if not obj.meta_description:
            issues.append("No meta desc")
        if not obj.focus_keyword:
            issues.append("No keyword")
        if not issues:
            return format_html('<span style="color:green;">✓</span>')
        return format_html(
            '<span style="color:orange;" title="{}">{}</span>',
            "; ".join(issues), f"{len(issues)} issue{'s' if len(issues)>1 else ''}",
        )

    seo_check.short_description = "SEO"
