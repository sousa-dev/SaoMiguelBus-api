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

    class Meta:
        ordering = ['-occurred_at']
        unique_together = [('island', 'emsc_id')]

    def __str__(self) -> str:
        return f'M{self.magnitude} {self.emsc_id}'


class FeltReport(TenantScopedModel):
    event = models.ForeignKey(SeismicEvent, on_delete=models.CASCADE, related_name='felt_reports')
    session_hash = models.CharField(max_length=64, db_index=True)
    intensity = models.PositiveSmallIntegerField()
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    reported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-reported_at']

    def __str__(self) -> str:
        return f'felt {self.intensity} on {self.event_id}'
