"""Domain exceptions for the stripe_payments app."""

from __future__ import annotations


class PaymentConfigurationError(Exception):
    """Raised when required Stripe settings are missing or empty."""

    def __init__(self, setting_name: str, *, debug: bool) -> None:
        prefix = "TEST_" if debug else ""
        env_var = f"{prefix}{setting_name}"
        hint = (
            f"Set {env_var} in your environment. "
            f"When DEBUG=False, djast uses unprefixed Stripe variables "
            f"(even if the values are Stripe test-mode keys)."
        )
        super().__init__(f"Stripe checkout is misconfigured: {env_var} is empty. {hint}")
        self.setting_name = setting_name
        self.env_var = env_var
