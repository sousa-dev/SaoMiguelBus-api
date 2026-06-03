from django.apps import AppConfig


class TransitConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'transit'
    verbose_name = 'Transit schedules'

    def ready(self) -> None:
        from transit.signals import register_transit_signals

        register_transit_signals()
