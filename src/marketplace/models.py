"""Marketplace: local service provider directory with moderated UGC."""

from __future__ import annotations

from django.db import models

from tenancy.models import TenantScopedModel


class ModeratedModel(models.Model):
    """Mixin for session-owned, moderated user-generated content.

    Reused by every UGC row (providers, reviews, and later events/traffic).
    Public reads must filter ``status=PUBLISHED``; owners (matched by the
    pseudonymous ``created_by_session_hash``) and staff also see their own
    non-published rows.
    """

    PENDING = 'pending'
    PUBLISHED = 'published'
    REJECTED = 'rejected'
    DELETED = 'deleted'
    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (PUBLISHED, 'Published'),
        (REJECTED, 'Rejected'),
        (DELETED, 'Deleted'),
    ]

    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=PENDING, db_index=True
    )
    created_by_session_hash = models.CharField(max_length=64, db_index=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def is_owned_by(self, session_hash: str) -> bool:
        return bool(session_hash) and self.created_by_session_hash == session_hash


class ServiceCategory(TenantScopedModel):
    """Admin-managed category for service providers (not moderated UGC)."""

    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80)
    icon = models.CharField(max_length=64, blank=True, default='')
    user_suggested = models.BooleanField(
        default=False,
        help_text='Created by a user when listing a service; review name/slug in admin.',
    )

    class Meta:
        ordering = ['name']
        unique_together = [('island', 'slug')]
        verbose_name_plural = 'Service categories'

    def __str__(self) -> str:
        return self.name


class ServiceProvider(TenantScopedModel, ModeratedModel):
    """A local tradesperson / service listing. Free; moderated before public."""

    name = models.CharField(max_length=160)
    category = models.ForeignKey(
        ServiceCategory, on_delete=models.PROTECT, related_name='providers'
    )
    bio = models.TextField(blank=True, default='')
    hourly_rate = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    phone = models.CharField(max_length=32, blank=True, default='')
    whatsapp = models.CharField(max_length=32, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    website = models.URLField(blank=True, default='', max_length=300)
    socials = models.JSONField(default=list, blank=True)
    claimed_owner = models.BooleanField(
        default=False,
        help_text='Submitter declared they are the business owner.',
    )
    internal_email = models.EmailField(
        blank=True,
        default='',
        help_text='Owner contact for SMB Hub staff only; not shown on public listings.',
    )
    internal_phone = models.CharField(
        max_length=32,
        blank=True,
        default='',
        help_text='Owner contact for SMB Hub staff only; not shown on public listings.',
    )
    verified_by_owner = models.BooleanField(
        default=False,
        db_index=True,
        help_text='Staff-confirmed business ownership; set only in Django admin.',
    )
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    is_promoted = models.BooleanField(default=False)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    review_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-is_promoted', 'name']  # admin only; public list sort is in services.list_providers
        indexes = [models.Index(fields=['island', 'status'])]

    def __str__(self) -> str:
        return self.name


class Review(TenantScopedModel, ModeratedModel):
    """A 1-5 star review of a provider, one per session per provider."""

    provider = models.ForeignKey(
        ServiceProvider, on_delete=models.CASCADE, related_name='reviews'
    )
    rating = models.PositiveSmallIntegerField()
    text = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-created_at']
        unique_together = [('provider', 'created_by_session_hash')]

    def __str__(self) -> str:
        return f'{self.rating}* on {self.provider_id}'
