"""User management models."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class SocialConnection(models.Model):
    """Links a Django user to a native social identity (Apple/Google).

    For Apple we also persist the refresh token so the account can be revoked
    via Apple's REST API when the user deletes their account (App Store
    Guideline 5.1.1(v) / Sign in with Apple requirements).
    """

    PROVIDER_APPLE = 'apple'
    PROVIDER_GOOGLE = 'google'
    PROVIDER_CHOICES = [(PROVIDER_APPLE, 'Apple'), (PROVIDER_GOOGLE, 'Google')]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='social_connections',
    )
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    subject = models.CharField(max_length=255, blank=True)
    # Apple refresh token — needed to revoke the grant on account deletion.
    refresh_token = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_social_connection'
        constraints = [
            models.UniqueConstraint(fields=['user', 'provider'], name='uniq_social_user_provider'),
        ]
        indexes = [models.Index(fields=['provider', 'subject'])]

    def __str__(self) -> str:
        return f'{self.user_id} · {self.provider}'
