"""GDPR consent records (CMP backend)."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class ConsentRecord(models.Model):
    """Granular consent choices per user or anonymous session."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='consent_records',
    )
    session_hash = models.CharField(max_length=64, db_index=True, blank=True, default='')
    purposes = models.JSONField(default=dict)
    policy_version = models.CharField(max_length=32)
    granted_at = models.DateTimeField(auto_now_add=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-granted_at']
        indexes = [
            models.Index(fields=['session_hash', '-granted_at']),
        ]

    def __str__(self) -> str:
        return f'consent {self.session_hash or self.user_id} @ {self.granted_at}'
