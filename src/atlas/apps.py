from django.apps import AppConfig


class AtlasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'atlas'
    verbose_name = 'Atlas'

    def ready(self):
        import atlas.signals  # noqa: F401
