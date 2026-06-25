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


class ParishProximity(TenantScopedModel):
    """Lazy mapping from a module-specific coordinate source to the nearest parish."""

    source_module = models.CharField(max_length=64, db_index=True)
    source_ref = models.CharField(max_length=128, db_index=True)
    parish = models.ForeignKey(Parish, on_delete=models.CASCADE, related_name='proximity_mappings')
    distance_km = models.FloatField()
    latitude = models.FloatField()
    longitude = models.FloatField()

    class Meta:
        unique_together = [('island', 'source_module', 'source_ref')]
        indexes = [
            models.Index(fields=['island', 'source_module', 'source_ref']),
        ]

    def __str__(self) -> str:
        return f'{self.source_module}:{self.source_ref} → {self.parish.slug}'
