"""EMSC seismic events and felt reports."""

from __future__ import annotations

from django.db import models

from tenancy.models import TenantScopedModel


class SeismicEvent(TenantScopedModel):
    emsc_id = models.CharField(max_length=64)
    magnitude = models.FloatField()
    depth_km = models.FloatField(null=True, blank=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    occurred_at = models.DateTimeField(db_index=True)
    region = models.CharField(max_length=200, blank=True, default='')
    nearest_island_key = models.CharField(max_length=32, null=True, blank=True)
    nearest_island_name = models.CharField(max_length=64, null=True, blank=True)
    nearest_island_distance_km = models.FloatField(null=True, blank=True)
    nearest_island_bearing = models.CharField(max_length=4, null=True, blank=True)

    class Meta:
        ordering = ['-occurred_at']
        unique_together = [('island', 'emsc_id')]

    def __str__(self) -> str:
        return f'M{self.magnitude} {self.emsc_id}'


class FeltReport(TenantScopedModel):
    event = models.ForeignKey(SeismicEvent, on_delete=models.CASCADE, related_name='felt_reports')
    session_hash = models.CharField(max_length=64, db_index=True)
    felt = models.BooleanField(default=True)
    intensity = models.PositiveSmallIntegerField(null=True, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    reported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-reported_at']

    def __str__(self) -> str:
        if not self.felt:
            return f'not felt on {self.event_id}'
        if self.intensity is not None:
            return f'felt {self.intensity} on {self.event_id}'
        return f'felt (no intensity) on {self.event_id}'
