from django.apps import AppConfig


class CompatConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'compat'
    verbose_name = 'Legacy API compatibility'
