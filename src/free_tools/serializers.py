"""Free tools API serializers."""

from __future__ import annotations

from rest_framework import serializers

from free_tools.models import FreeTool, ToolCategory


class ToolCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ToolCategory
        fields = ["id", "name", "slug", "description", "icon_class"]
        read_only_fields = ["id"]


class FreeToolListSerializer(serializers.ModelSerializer):
    category = ToolCategorySerializer(read_only=True)
    url = serializers.SerializerMethodField()

    class Meta:
        model = FreeTool
        fields = [
            "id", "name", "slug", "tagline", "icon_class",
            "language", "category", "status",
            "published_at", "updated_at", "sort_order", "url",
        ]
        read_only_fields = ["id"]

    def get_url(self, obj: FreeTool) -> str:
        return obj.get_absolute_url()


class FreeToolDetailSerializer(serializers.ModelSerializer):
    category = ToolCategorySerializer(read_only=True)
    translations = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()

    class Meta:
        model = FreeTool
        fields = [
            "id", "name", "slug", "tagline", "description",
            "template_name", "meta_title", "meta_description",
            "focus_keyword", "canonical_url", "noindex",
            "og_image", "icon_class",
            "language", "category", "status",
            "published_at", "updated_at", "created_at",
            "sort_order", "cta_text", "cta_url", "lead_magnet_title",
            "translation_group", "translations", "url",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_translations(self, obj: FreeTool) -> list[dict]:
        return [
            {"language": t.language, "slug": t.slug, "name": t.name}
            for t in obj.get_translations()
        ]

    def get_url(self, obj: FreeTool) -> str:
        return obj.get_absolute_url()


class FreeToolWriteSerializer(serializers.ModelSerializer):
    """Write serializer — accepts ``category_slug`` instead of FK ID."""

    category_slug = serializers.SlugField(write_only=True, required=False)

    class Meta:
        model = FreeTool
        fields = [
            "name", "slug", "tagline", "description", "template_name",
            "meta_title", "meta_description", "focus_keyword",
            "canonical_url", "noindex", "og_image", "icon_class",
            "language", "status", "sort_order",
            "cta_text", "cta_url", "lead_magnet_title",
            "category_slug", "translation_group",
        ]

    def create(self, validated_data: dict) -> FreeTool:
        cat_slug = validated_data.pop("category_slug", "")
        tool = FreeTool(**validated_data)
        if cat_slug:
            tool.category = ToolCategory.objects.filter(slug=cat_slug).first()
        tool.save()
        return tool

    def update(self, instance: FreeTool, validated_data: dict) -> FreeTool:
        cat_slug = validated_data.pop("category_slug", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if cat_slug is not None:
            instance.category = ToolCategory.objects.filter(slug=cat_slug).first()
        instance.save()
        return instance
