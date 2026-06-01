"""Legacy email subscription allow-list (compat with old subscriptions app)."""

from django.core.validators import EmailValidator
from django.db import models


class Subscription(models.Model):
    id = models.AutoField(primary_key=True)
    email = models.EmailField(validators=[EmailValidator()], unique=True)
    is_active = models.BooleanField(default=True)
    verification_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subscriptions'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self) -> str:
        status = 'Active' if self.is_active else 'Inactive'
        return f'{self.email} - {status}'
