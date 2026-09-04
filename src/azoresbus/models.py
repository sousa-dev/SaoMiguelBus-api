"""Upstream-facing state: external identity, sync bookkeeping, tariffs.

The schedule data itself lives in `transit` models so search, the offline
bundle, directions and trip detail keep working unchanged. What lives here is
everything that only matters because the data came from somewhere else.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone

from tenancy.models import TenantScopedModel
from transit.models import DATASET_AZORESBUS, DATASET_CHOICES


class SyncRun(TenantScopedModel):
    """One execution of the sync worker.

    `sampled_dates` is first-class rather than buried in `stats`: a run's
    correctness depends on WHICH dates it sampled, and it is the only way to
    know later whether a pattern came from a term week, a summer week, or a
    poisoned holiday (02 section 3.7).
    """

    KIND_SCHEDULES = 'schedules'
    KIND_TARIFFS = 'tariffs'
    KIND_CHOICES = [(KIND_SCHEDULES, 'Schedules'), (KIND_TARIFFS, 'Tariffs')]

    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_PARTIAL = 'partial'
    STATUS_CHOICES = [
        (STATUS_RUNNING, 'Running'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_PARTIAL, 'Partial'),
    ]

    kind = models.CharField(max_length=16, choices=KIND_CHOICES,
                            default=KIND_SCHEDULES, db_index=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES,
                              default=STATUS_RUNNING, db_index=True)
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    request_count = models.PositiveIntegerField(default=0)
    sampled_dates = models.JSONField(default=list)
    stats = models.JSONField(default=dict)
    error = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-started_at']
        indexes = [models.Index(fields=['island', 'kind', 'status', '-started_at'])]

    def __str__(self) -> str:
        return f'{self.kind} {self.status} @ {self.started_at:%Y-%m-%d %H:%M}'


class ExternalStop(TenantScopedModel):
    """An upstream stop code -- one physical pole.

    1456 upstream stops collapse to 816 `transit.Stop` rows by name, because a
    tourist cannot choose a pole before choosing a destination. Which pole a
    trip actually serves is a property of its direction, and it is kept here so
    the boarding marker lands on the correct side of the road and a live
    vehicle's currentStopSequence resolves to a real place.
    """

    dataset = models.CharField(max_length=16, choices=DATASET_CHOICES,
                               default=DATASET_AZORESBUS, db_index=True)
    external_id = models.CharField(max_length=32, db_index=True)   # stage.id
    code = models.CharField(max_length=32, db_index=True)          # nameShort
    name = models.CharField(max_length=200)                        # verbatim
    latitude = models.FloatField()
    longitude = models.FloatField()
    stop = models.ForeignKey('transit.Stop', on_delete=models.CASCADE,
                             related_name='external_stops')

    class Meta:
        unique_together = [('island', 'dataset', 'external_id')]
        ordering = ['code']

    def __str__(self) -> str:
        return f'{self.code} {self.name}'


class ExternalJourney(TenantScopedModel):
    """An upstream journey and the trip we built from it."""

    dataset = models.CharField(max_length=16, choices=DATASET_CHOICES,
                               default=DATASET_AZORESBUS, db_index=True)
    external_id = models.CharField(max_length=32, db_index=True)
    route_ext_id = models.CharField(max_length=32, db_index=True)
    direction = models.PositiveSmallIntegerField(default=0)
    shape = models.TextField(blank=True, default='')     # encoded polyline
    # Hash of the DETAIL body. It skips DB WRITES, never GETs: the listing
    # carries no shape and no circulations, so the hash is only knowable after
    # fetching the detail (98 section 4 gap).
    payload_hash = models.CharField(max_length=64, blank=True, default='')
    # f'{route}|{start}|{end}'. A journey id is not a stable content key across
    # a republish, so this is what makes id churn detectable (98 section 7).
    identity = models.CharField(max_length=128, blank=True, default='')
    trip = models.ForeignKey('transit.Trip', on_delete=models.CASCADE,
                             related_name='external_journeys')

    class Meta:
        unique_together = [('island', 'dataset', 'external_id')]
        ordering = ['external_id']

    def __str__(self) -> str:
        return f'{self.route_ext_id}/{self.external_id}'


class ServiceObservation(TenantScopedModel):
    """One row per (journey, sampled date) where upstream returned the journey.

    The ground truth the ServicePattern rules are derived from. Keeping it means
    a later sample can re-derive without re-fetching, a pattern change is
    diffable rather than mysterious, and the prune can tell "out of season" from
    "deleted" (02 section 4.5 rule 4).
    """

    dataset = models.CharField(max_length=16, choices=DATASET_CHOICES,
                               default=DATASET_AZORESBUS, db_index=True)
    external_id = models.CharField(max_length=32, db_index=True)
    date = models.DateField(db_index=True)
    run = models.ForeignKey(SyncRun, on_delete=models.CASCADE,
                            related_name='observations')

    class Meta:
        unique_together = [('island', 'dataset', 'external_id', 'date')]
        indexes = [models.Index(fields=['island', 'dataset', 'date'])]

    def __str__(self) -> str:
        return f'{self.external_id} on {self.date}'


class TariffSnapshot(TenantScopedModel):
    """Append-only fare snapshots, one row per distinct content hash.

    Stored schemaless on purpose: all 148 `fareUnits` values are human-readable
    band labels ("0 a 5", "6 a 7", "8"), and the category/group/tariff nesting is
    the operator's editorial structure, which will change without warning.
    Parsing it into relational tables buys nothing and breaks on the first
    restructure (02 section 6).
    """

    source_url = models.URLField(max_length=255)
    effective_date = models.DateField(null=True, blank=True)   # payload "date"
    upstream_etag = models.CharField(max_length=128, blank=True, default='')
    upstream_modified_at = models.DateTimeField(null=True, blank=True)
    fetched_at = models.DateTimeField(default=timezone.now)
    payload = models.JSONField(default=dict)
    content_hash = models.CharField(max_length=64, db_index=True)
    is_current = models.BooleanField(default=True)

    class Meta:
        ordering = ['-effective_date', '-fetched_at']
        indexes = [models.Index(fields=['island', 'is_current'])]

    def __str__(self) -> str:
        return f'tariffs {self.effective_date} ({self.content_hash[:8]})'


class LiveActivityRegistration(TenantScopedModel):
    """An iOS Live Activity that wants push updates for a tracked trip.

    Stores no personal data -- a push token, the trip ids the rider is
    tracking, and when to stop pushing. `push_token` is an ActivityKit
    push-to-update token, not a device token and not an Expo push token; the
    Expo push service does not proxy the `liveactivity` APNs push type, so
    this is sent to Apple directly (`azoresbus/apns.py`).

    `ended_at` rather than deleting on unregister: the beat task
    (`azoresbus.push_live_activities`) still owes the Live Activity a final
    `event: "end"` push so it dismisses itself cleanly rather than sitting on
    the Lock Screen frozen until Apple's own ceiling expires it.
    """

    ENVIRONMENT_DEVELOPMENT = 'development'
    ENVIRONMENT_PRODUCTION = 'production'
    ENVIRONMENT_CHOICES = [
        (ENVIRONMENT_DEVELOPMENT, 'Development'),
        (ENVIRONMENT_PRODUCTION, 'Production'),
    ]

    push_token = models.CharField(max_length=200, unique=True, db_index=True)
    environment = models.CharField(max_length=16, choices=ENVIRONMENT_CHOICES)
    activity_key = models.CharField(max_length=64, blank=True, default='')
    # [{'tripId': int, 'startsAt': iso str, 'endsAt': iso str}, ...]
    legs = models.JSONField(default=list)
    expires_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    last_pushed_at = models.DateTimeField(null=True, blank=True)
    failure_count = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=['island', 'ended_at', 'expires_at']),
        ]

    def __str__(self) -> str:
        return f'live activity {self.activity_key or self.pk} ({self.environment})'
