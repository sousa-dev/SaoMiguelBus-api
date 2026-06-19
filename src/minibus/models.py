"""PDL Mini Bus — Ponta Delgada urban network."""

from __future__ import annotations

from django.db import models

from tenancy.models import TenantScopedModel


class MinibusLine(TenantScopedModel):
    code = models.CharField(max_length=4)
    slug = models.SlugField(max_length=32)
    name_pt = models.CharField(max_length=120)
    name_en = models.CharField(max_length=120)
    color = models.CharField(max_length=7)
    sort_order = models.PositiveSmallIntegerField(default=0)
    service_summary = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['sort_order', 'code']
        unique_together = [('island', 'slug'), ('island', 'code')]
        indexes = [
            models.Index(fields=['island', 'is_active']),
        ]

    def __str__(self) -> str:
        return f'{self.code} ({self.slug})'


class MinibusTariff(TenantScopedModel):
    key = models.SlugField(max_length=64)
    label_pt = models.CharField(max_length=160)
    label_en = models.CharField(max_length=160)
    price_eur = models.DecimalField(max_digits=6, decimal_places=2)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['sort_order', 'key']
        unique_together = [('island', 'key')]

    def __str__(self) -> str:
        return self.key


class MinibusDocument(TenantScopedModel):
    DOC_TIMETABLE = 'timetable'
    DOC_NETWORK_MAP = 'network_map'
    DOC_TARIFFS = 'tariffs'
    DOC_SCHEMATIC = 'schematic'
    DOC_TYPE_CHOICES = [
        (DOC_TIMETABLE, 'Timetable'),
        (DOC_NETWORK_MAP, 'Network map'),
        (DOC_TARIFFS, 'Tariffs'),
        (DOC_SCHEMATIC, 'Schematic'),
    ]

    slug = models.SlugField(max_length=64)
    title_pt = models.CharField(max_length=160)
    title_en = models.CharField(max_length=160)
    doc_type = models.CharField(max_length=32, choices=DOC_TYPE_CHOICES)
    source_filename = models.CharField(max_length=255)
    file = models.FileField(upload_to='minibus/', blank=True)
    line = models.ForeignKey(
        MinibusLine,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='documents',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['doc_type', 'slug']
        unique_together = [('island', 'slug')]

    def __str__(self) -> str:
        return self.slug


class MinibusImportMeta(TenantScopedModel):
    source_url = models.URLField(max_length=255)
    source_revision = models.CharField(max_length=64, blank=True, default='')
    imported_at = models.DateTimeField(null=True, blank=True)
    tariffs_effective_date = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = 'Mini Bus import metadata'
        verbose_name_plural = 'Mini Bus import metadata'

    def __str__(self) -> str:
        return f'{self.island.key} import meta'
