"""Traffic: crowdsourced live road alerts (instant-publish UGC).

Unlike ``marketplace``, traffic reports are **public on create** — there is no
pending-moderation queue. ``status`` is a lifecycle field
(``active``/``scheduled``/``expired``/``removed``) driven by a Celery task and
by confirm/deny voting. Trust comes from per-session throttling, voting, and
auto-expiry rather than pre-publication review.
"""

from __future__ import annotations

from django.db import models

from tenancy.models import TenantScopedModel


class TrafficCategory(TenantScopedModel):
    """Admin-managed, seeded report category for the quick-pick reporter."""

    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80)
    icon = models.CharField(max_length=64, blank=True, default='')
    default_ttl_minutes = models.PositiveIntegerField(
        default=120,
        help_text='How long a fresh report of this category stays active.',
    )
    is_schedulable = models.BooleanField(
        default=False,
        help_text='Allow pre-announced reports with a future active_from (e.g. radar).',
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'name']
        unique_together = [('island', 'slug')]
        verbose_name_plural = 'Traffic categories'

    def __str__(self) -> str:
        return self.name


class TrafficReport(TenantScopedModel):
    """A single crowdsourced road alert. Public immediately on create."""

    ACTIVE = 'active'
    SCHEDULED = 'scheduled'
    EXPIRED = 'expired'
    REMOVED = 'removed'
    STATUS_CHOICES = [
        (ACTIVE, 'Active'),
        (SCHEDULED, 'Scheduled'),
        (EXPIRED, 'Expired'),
        (REMOVED, 'Removed'),
    ]

    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=ACTIVE, db_index=True
    )
    category = models.ForeignKey(
        TrafficCategory, on_delete=models.PROTECT, related_name='reports'
    )
    created_by_session_hash = models.CharField(max_length=64, db_index=True, blank=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    description = models.TextField(blank=True, default='')
    road = models.CharField(max_length=160, blank=True, default='')
    active_from = models.DateTimeField(null=True, blank=True)
    active_until = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(db_index=True)
    confirm_count = models.PositiveIntegerField(default=0)
    deny_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['island', 'status', 'expires_at'])]

    def __str__(self) -> str:
        return f'{self.category_id} @ {self.latitude},{self.longitude} ({self.status})'

    def is_owned_by(self, session_hash: str) -> bool:
        return bool(session_hash) and self.created_by_session_hash == session_hash


class TrafficConfirmation(TenantScopedModel):
    """A 'still there' / 'gone' vote, one per session per report."""

    STILL_THERE = 'still_there'
    GONE = 'gone'
    VOTE_CHOICES = [
        (STILL_THERE, 'Still there'),
        (GONE, 'Gone'),
    ]

    report = models.ForeignKey(
        TrafficReport, on_delete=models.CASCADE, related_name='confirmations'
    )
    session_hash = models.CharField(max_length=64, db_index=True)
    vote = models.CharField(max_length=16, choices=VOTE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = [('report', 'session_hash')]

    def __str__(self) -> str:
        return f'{self.vote} on {self.report_id}'
