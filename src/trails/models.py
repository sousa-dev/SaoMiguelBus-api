"""Trails and points of interest (dados.gov.pt sync target)."""

from __future__ import annotations

from django.db import models

from tenancy.models import TenantScopedModel


class Trail(TenantScopedModel):
    source_ref = models.CharField(max_length=128)
    name = models.CharField(max_length=200)
    difficulty = models.CharField(max_length=32, blank=True, default='')
    distance_km = models.FloatField(null=True, blank=True)
    geojson = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['name']
        unique_together = [('island', 'source_ref')]

    def __str__(self) -> str:
        return self.name


class TrailStage(TenantScopedModel):
    trail = models.ForeignKey(Trail, on_delete=models.CASCADE, related_name='stages')
    name = models.CharField(max_length=200)
    sequence = models.PositiveIntegerField(default=1)
    geojson = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['sequence']

    def __str__(self) -> str:
        return f'{self.trail.name} — {self.name}'


class POI(TenantScopedModel):
    source_ref = models.CharField(max_length=128)
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=64, blank=True, default='')
    latitude = models.FloatField()
    longitude = models.FloatField()

    class Meta:
        ordering = ['name']
        unique_together = [('island', 'source_ref')]
        verbose_name = 'POI'
        verbose_name_plural = 'POIs'

    def __str__(self) -> str:
        return self.name
