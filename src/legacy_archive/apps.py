from django.apps import AppConfig


class LegacyArchiveConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'legacy_archive'
    verbose_name = 'Legacy archive'
