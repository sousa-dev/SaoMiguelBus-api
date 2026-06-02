"""Island tenant root and scoped base model."""

from __future__ import annotations

import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from tenancy.managers import TenantManager


class Island(models.Model):
    """Deployment tenant root (alias Hub)."""

    key = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=120)
    archipelago = models.CharField(max_length=64, default='Azores')
    is_live = models.BooleanField(default=False)
    center_lat = models.FloatField(default=37.7822)
    center_lng = models.FloatField(default=-25.4998)
    radius_km = models.PositiveIntegerField(default=50)
    timezone = models.CharField(max_length=64, default='Atlantic/Azores')
    default_locale = models.CharField(max_length=8, default='pt')
    locales = models.JSONField(default=list)
    theme = models.JSONField(default=dict, blank=True)
    feature_flags = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self) -> str:
        return self.name

    @classmethod
    def default_sao_miguel(cls) -> dict:
        """Seed values for the first island migration step."""
        return {
            'key': 'sao-miguel',
            'name': 'São Miguel',
            'archipelago': 'Azores',
            'is_live': True,
            'center_lat': 37.782213,
            'center_lng': -25.499806,
            'radius_km': 50,
            'timezone': 'Atlantic/Azores',
            'default_locale': 'pt',
            'locales': ['pt', 'en', 'es', 'fr', 'de', 'it', 'nl', 'pl'],
            'theme': {
                'primaryColor': '#28a745',
                'secondaryColor': '#1e7e34',
                'accentColor': '#ffc107',
            },
            'feature_flags': {
                'transit': True,
                'news': False,
                'seismic': False,
                'marketplace': False,
                'trails': False,
                'traffic': False,
                'events': False,
            },
        }


class LegacyImportJob(models.Model):
    """Background legacy ETL job (runs via Celery worker)."""

    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    job_id = models.CharField(max_length=32, unique=True, editable=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    island_key = models.SlugField(max_length=64, default='sao-miguel')
    export_file_path = models.CharField(max_length=500, blank=True)
    legacy_db_url = models.CharField(max_length=500, blank=True)
    skip_steps = models.JSONField(default=list, blank=True)
    current_step = models.CharField(max_length=64, blank=True)
    step_reports = models.JSONField(default=list, blank=True)
    table_counts = models.JSONField(null=True, blank=True)
    celery_task_id = models.CharField(max_length=64, blank=True)
    error = models.TextField(blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at']
        verbose_name = 'Legacy import job'
        verbose_name_plural = 'Legacy import jobs'

    def __str__(self) -> str:
        return f'{self.job_id} ({self.status})'

    @classmethod
    def new_job_id(cls) -> str:
        return uuid.uuid4().hex[:16]


class TenantScopedModel(models.Model):
    """Abstract base: every domain row belongs to an island."""

    island = models.ForeignKey(Island, on_delete=models.PROTECT, db_index=True)
    legacy_ref = models.JSONField(default=dict, blank=True)

    objects = TenantManager()

    class Meta:
        abstract = True
