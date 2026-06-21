"""User personalization profiles."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class PersonalizationProfile(models.Model):
    USER_TYPE_CHOICES = [
        ('tourist', 'Tourist'),
        ('resident', 'Resident'),
        ('newcomer', 'Newcomer'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='personalization_profiles',
    )
    session_hash = models.CharField(max_length=64, db_index=True, blank=True, default='')
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES)
    interests = models.JSONField(default=list)
    home_municipality = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['session_hash', '-updated_at']),
        ]

    def __str__(self) -> str:
        return f'personalization {self.session_hash or self.user_id} ({self.user_type})'
