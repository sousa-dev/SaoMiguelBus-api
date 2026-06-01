"""Legacy-compatible stat model (Phase 1 compat writes)."""

from django.db import models


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
