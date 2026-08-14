"""AzoresBus sync, tariffs and tracking.

The schedule data itself lands in ``transit`` models so search, the offline
bundle, directions and trip detail keep working unchanged. This app owns the
upstream-facing concerns: the rate-limited client, the sampling sync worker,
service-pattern derivation, tariffs and tracking.
"""

from __future__ import annotations

from django.apps import AppConfig


class AzoresbusConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'azoresbus'
    verbose_name = 'AzoresBus'
