"""Analytics models — legacy Stat (compat) + v3 AnalyticsEvent."""

from django.db import models

from tenancy.models import TenantScopedModel


class AnalyticsEvent(TenantScopedModel):
    """Normalized first-party analytics event (v3)."""

    MODULE_TRANSIT = 'transit'
    MODULE_NEWS = 'news'
    MODULE_SEISMIC = 'seismic'
    MODULE_MARKETPLACE = 'marketplace'
    MODULE_TRAILS = 'trails'
    MODULE_TRAFFIC = 'traffic'
    MODULE_EVENTS = 'events'
    MODULE_MINIBUS = 'minibus'

    module = models.CharField(max_length=32, db_index=True)
    event_type = models.CharField(max_length=32, db_index=True)
    properties = models.JSONField(default=dict, blank=True)
    session_hash = models.CharField(max_length=64, blank=True, default='', db_index=True)
    consent_state = models.JSONField(default=dict, blank=True)
    platform = models.CharField(max_length=16, default='web')
    locale = models.CharField(max_length=8, default='pt')
    app_version = models.CharField(max_length=32, blank=True, default='')
    occurred_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table = 'analytics_event'
        ordering = ['-occurred_at']
        indexes = [
            models.Index(fields=['island', 'module', 'occurred_at']),
        ]

    def __str__(self) -> str:
        return f'{self.module}.{self.event_type} @ {self.occurred_at}'


class Stat(models.Model):
    request = models.CharField(max_length=100)
    origin = models.CharField(max_length=100, default='')
    destination = models.CharField(max_length=100, default='')
    type_of_day = models.CharField(max_length=100, default='NA')
    time = models.CharField(max_length=100, default='NA')
    platform = models.CharField(max_length=100, default='NA')
    language = models.CharField(max_length=100, default='NA')
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'analytics_stat'
        indexes = [
            models.Index(fields=['request', 'timestamp']),
        ]

    def __str__(self) -> str:
        return f'{self.request} | {self.origin} -> {self.destination}'
