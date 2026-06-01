"""Blog API serializers.

Used by the DRF API views for CRUD operations on blog posts,
categories, and tags. Designed for agent and programmatic access.
"""

from __future__ import annotations

from rest_framework import serializers

from blog.models import BlogPost, Category, Tag


class CategorySerializer(serializers.ModelSerializer):
    """Serializer for blog categories."""

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "description", "parent"]
        read_only_fields = ["id"]


class TagSerializer(serializers.ModelSerializer):
    """Serializer for blog tags."""

    class Meta:
        model = Tag
        fields = ["id", "name", "slug"]
        read_only_fields = ["id"]


class BlogPostListSerializer(serializers.ModelSerializer):
    """Compact serializer for blog post listings."""

    category = CategorySerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    author_name = serializers.SerializerMethodField()
    reading_time = serializers.IntegerField(
        source="reading_time_minutes", read_only=True
    )
    url = serializers.SerializerMethodField()

    class Meta:
        model = BlogPost
        fields = [
            "id", "title", "slug", "excerpt", "effective_excerpt",
            "language", "category", "tags", "author_name",
            "status", "published_at", "updated_at",
            "reading_time", "word_count", "featured_image",
            "featured_image_alt", "url",
        ]
        read_only_fields = ["id", "word_count", "effective_excerpt"]

    def get_author_name(self, obj: BlogPost) -> str:
        if obj.author:
            return obj.author.get_full_name() or obj.author.username
        return ""

    def get_url(self, obj: BlogPost) -> str:
        return obj.get_absolute_url()


class BlogPostDetailSerializer(serializers.ModelSerializer):
    """Full serializer for reading a single blog post."""

    category = CategorySerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    author_name = serializers.SerializerMethodField()
    reading_time = serializers.IntegerField(
        source="reading_time_minutes", read_only=True
    )
    translations = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()

    class Meta:
        model = BlogPost
        fields = [
            "id", "title", "slug", "body", "excerpt", "effective_excerpt",
            "meta_title", "meta_description", "focus_keyword",
            "canonical_url", "noindex",
            "featured_image", "featured_image_alt", "og_image",
            "language", "category", "tags", "author_name",
            "status", "published_at", "updated_at", "created_at",
            "reading_time", "word_count",
            "cta_text", "cta_url", "lead_magnet_title",
            "translation_group", "translations", "url",
        ]
        read_only_fields = [
            "id", "word_count", "created_at", "updated_at",
            "effective_excerpt",
        ]

    def get_author_name(self, obj: BlogPost) -> str:
        if obj.author:
            return obj.author.get_full_name() or obj.author.username
        return ""

    def get_translations(self, obj: BlogPost) -> list[dict]:
        return [
            {"language": t.language, "slug": t.slug, "title": t.title}
            for t in obj.get_translations()
        ]

    def get_url(self, obj: BlogPost) -> str:
        return obj.get_absolute_url()


class BlogPostWriteSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating blog posts via the API.

    Accepts ``category_slug`` and ``tag_slugs`` as write-only fields
    so agents don't need to know internal IDs.
    """

    category_slug = serializers.SlugField(write_only=True, required=False)
    tag_slugs = serializers.ListField(
        child=serializers.SlugField(), write_only=True, required=False
    )
    translation_of_slug = serializers.SlugField(
        write_only=True, required=False,
        help_text="Slug of an existing post to link as a translation.",
    )

    class Meta:
        model = BlogPost
        fields = [
            "title", "slug", "body", "excerpt",
            "meta_title", "meta_description", "focus_keyword",
            "canonical_url", "noindex",
            "featured_image", "featured_image_alt", "og_image",
            "language", "status",
            "category_slug", "tag_slugs",
            "cta_text", "cta_url", "lead_magnet_title",
            "translation_of_slug",
        ]

    def create(self, validated_data: dict) -> BlogPost:
        from blog.services import CreatePostInput, create_post

        tag_slugs = validated_data.pop("tag_slugs", [])
        category_slug = validated_data.pop("category_slug", "")
        translation_of_slug = validated_data.pop("translation_of_slug", "")

        request = self.context.get("request")
        author_id = request.user.id if request and request.user.is_authenticated else None

        data = CreatePostInput(
            author_id=author_id,
            category_slug=category_slug,
            tag_slugs=tag_slugs,
            translation_of_slug=translation_of_slug,
            **validated_data,
        )
        return create_post(data)

    def update(self, instance: BlogPost, validated_data: dict) -> BlogPost:
        tag_slugs = validated_data.pop("tag_slugs", None)
        category_slug = validated_data.pop("category_slug", None)
        validated_data.pop("translation_of_slug", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if category_slug is not None:
            from blog.models import Category
            instance.category = Category.objects.filter(slug=category_slug).first()

        instance.save()

        if tag_slugs is not None:
            from blog.models import Tag
            tags = Tag.objects.filter(slug__in=tag_slugs)
            instance.tags.set(tags)

        return instance
