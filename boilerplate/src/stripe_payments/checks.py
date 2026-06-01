"""Django system checks for stripe_payments configuration."""

from __future__ import annotations

from django.apps import apps
from django.conf import settings
from django.core.checks import Error, Warning, register

_REQUIRED_SETTINGS = (
    "STRIPE_SECRET_KEY",
    "STRIPE_PUBLIC_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "PRODUCT_PRICE_ID",
    "REDIRECT_DOMAIN",
)


@register()
def check_stripe_configuration(app_configs, **kwargs) -> list[Error | Warning]:
    """Warn or error when Stripe settings are missing."""
    if app_configs is None:
        app_configs = apps.get_app_configs()

    if not any(app.label == "stripe_payments" for app in app_configs):
        return []

    issues: list[Error | Warning] = []
    prefix = "TEST_" if settings.DEBUG else ""
    check_id = "stripe_payments.E001"

    for setting_name in _REQUIRED_SETTINGS:
        value = getattr(settings, setting_name, "")
        if value:
            continue

        env_var = f"{prefix}{setting_name}"
        message = (
            f"{env_var} is not set. Stripe checkout and webhooks will fail. "
            f"When DEBUG=False, use unprefixed variable names "
            f"(values may still be Stripe test-mode keys)."
        )
        if settings.DEBUG:
            issues.append(Warning(message, id=check_id))
        else:
            issues.append(Error(message, id=check_id))

    return issues
