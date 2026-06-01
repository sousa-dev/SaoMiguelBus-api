"""Free tools app configuration."""

from __future__ import annotations

from django.apps import AppConfig


class FreeToolsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "free_tools"
    verbose_name = "Free Tools"
