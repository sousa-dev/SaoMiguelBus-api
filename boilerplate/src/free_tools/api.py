"""Free tools REST API views.

Endpoints:
    GET    /tools/api/tools/          — List published tools
    POST   /tools/api/tools/          — Create a tool
    GET    /tools/api/tools/<slug>/   — Retrieve by slug
    PUT    /tools/api/tools/<slug>/   — Full update
    PATCH  /tools/api/tools/<slug>/   — Partial update
    DELETE /tools/api/tools/<slug>/   — Delete
    GET    /tools/api/categories/     — List categories
    POST   /tools/api/categories/     — Create a category
"""

from __future__ import annotations

from rest_framework import generics, permissions, status
from rest_framework.response import Response

from free_tools.models import FreeTool, ToolCategory
from free_tools.serializers import (
    FreeToolDetailSerializer,
    FreeToolListSerializer,
    FreeToolWriteSerializer,
    ToolCategorySerializer,
)
from free_tools.services import get_published_tools


class ToolListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return FreeToolWriteSerializer
        return FreeToolListSerializer

    def get_queryset(self):
        return get_published_tools(
            category_slug=self.request.query_params.get("category"),
            search=self.request.query_params.get("q"),
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tool = serializer.save()
        return Response(
            FreeToolDetailSerializer(tool).data,
            status=status.HTTP_201_CREATED,
        )


class ToolDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    lookup_field = "slug"

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return FreeToolWriteSerializer
        return FreeToolDetailSerializer

    def get_queryset(self):
        if self.request.method == "GET":
            return FreeTool.objects.filter(status=FreeTool.Status.PUBLISHED).select_related("category")
        return FreeTool.objects.select_related("category")


class CategoryListCreateView(generics.ListCreateAPIView):
    queryset = ToolCategory.objects.all()
    serializer_class = ToolCategorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
