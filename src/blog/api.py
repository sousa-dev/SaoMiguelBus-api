"""Blog REST API views.

Full CRUD API for blog posts, categories, and tags. Designed for
programmatic access by AI agents and integrations.

Endpoints:
    GET    /blog/api/posts/          — List published posts (filterable)
    POST   /blog/api/posts/          — Create a new post
    GET    /blog/api/posts/<slug>/   — Retrieve a post by slug
    PUT    /blog/api/posts/<slug>/   — Full update
    PATCH  /blog/api/posts/<slug>/   — Partial update
    DELETE /blog/api/posts/<slug>/   — Delete a post
    GET    /blog/api/categories/     — List categories
    POST   /blog/api/categories/     — Create a category
    GET    /blog/api/tags/           — List tags
    POST   /blog/api/tags/           — Create a tag
"""

from __future__ import annotations

from rest_framework import generics, permissions, status
from rest_framework.response import Response

from blog.models import BlogPost, Category, Tag
from blog.serializers import (
    BlogPostDetailSerializer,
    BlogPostListSerializer,
    BlogPostWriteSerializer,
    CategorySerializer,
    TagSerializer,
)
from blog.services import get_published_posts


class PostListCreateView(generics.ListCreateAPIView):
    """List published posts or create a new one.

    Query params for filtering:
        - ``lang``: language code
        - ``category``: category slug
        - ``tag``: tag slug
        - ``q``: search query
        - ``sort``: sort field (default: ``-published_at``)
    """

    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return BlogPostWriteSerializer
        return BlogPostListSerializer

    def get_queryset(self):
        return get_published_posts(
            language=self.request.query_params.get("lang"),
            category_slug=self.request.query_params.get("category"),
            tag_slug=self.request.query_params.get("tag"),
            search=self.request.query_params.get("q"),
            sort=self.request.query_params.get("sort", "-published_at"),
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        post = serializer.save()
        return Response(
            BlogPostDetailSerializer(post).data,
            status=status.HTTP_201_CREATED,
        )


class PostDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a blog post by slug."""

    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    lookup_field = "slug"

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return BlogPostWriteSerializer
        return BlogPostDetailSerializer

    def get_queryset(self):
        if self.request.method == "GET":
            return (
                BlogPost.objects
                .filter(status=BlogPost.Status.PUBLISHED)
                .select_related("author", "category")
                .prefetch_related("tags")
            )
        return BlogPost.objects.select_related("author", "category").prefetch_related("tags")


class CategoryListCreateView(generics.ListCreateAPIView):
    """List all categories or create a new one."""

    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class TagListCreateView(generics.ListCreateAPIView):
    """List all tags or create a new one."""

    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
