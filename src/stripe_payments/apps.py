from django.apps import AppConfig


class StripePaymentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'stripe_payments'

    def ready(self) -> None:
        from stripe_payments import checks  # noqa: F401
