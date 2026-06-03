"""Parish locations for per-freguesia weather."""

from __future__ import annotations

from django.db import models

from tenancy.models import TenantScopedModel


class Parish(TenantScopedModel):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=160)
    concelho = models.CharField(max_length=80)
    latitude = models.FloatField()
    longitude = models.FloatField()
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [('island', 'slug')]
        ordering = ['concelho', 'name']
        indexes = [
            models.Index(fields=['island', 'concelho']),
            models.Index(fields=['island', 'is_active']),
        ]

    def __str__(self) -> str:
        return f'{self.name} ({self.concelho})'
