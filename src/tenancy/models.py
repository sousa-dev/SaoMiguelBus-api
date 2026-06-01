"""Island tenant root and scoped base model."""

from __future__ import annotations

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

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


class TenantScopedModel(models.Model):
    """Abstract base: every domain row belongs to an island."""

    island = models.ForeignKey(Island, on_delete=models.PROTECT, db_index=True)
    legacy_ref = models.JSONField(default=dict, blank=True)

    objects = TenantManager()

    class Meta:
        abstract = True
