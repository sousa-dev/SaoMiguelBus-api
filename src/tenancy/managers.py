"""Tenant-aware queryset managers."""

from __future__ import annotations

from django.db import models

from tenancy.context import get_active_island


class TenantManager(models.Manager):
    """Filters querysets by the active island when one is set."""

    def get_queryset(self) -> models.QuerySet:
        queryset = super().get_queryset()
        island = get_active_island()
        if island is not None:
            queryset = queryset.filter(island=island)
        return queryset

    def for_island(self, island) -> models.QuerySet:
        """Bypass request context and scope explicitly (Celery, imports, admin)."""
        return super().get_queryset().filter(island=island)

    def unscoped(self) -> models.QuerySet:
        """Return all rows regardless of active island."""
        return super().get_queryset()
