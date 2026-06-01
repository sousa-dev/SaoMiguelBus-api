"""Stripe payment service layer.

Encapsulates all Stripe-related business logic, keeping views thin and
making the payment flow explicit and testable.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

import stripe
from django.conf import settings
from django.core.mail import send_mail

from stripe_payments.exceptions import PaymentConfigurationError
from stripe_payments.models import UserPayment

logger = logging.getLogger(__name__)

_CHECKOUT_REQUIRED_SETTINGS = (
    "STRIPE_SECRET_KEY",
    "PRODUCT_PRICE_ID",
    "REDIRECT_DOMAIN",
)


@dataclass
class CheckoutResult:
    """Return value from ``create_checkout_session``."""

    session_id: str
    checkout_url: str


@dataclass
class PaymentConfirmation:
    """Return value from ``confirm_payment``."""

    customer_email: str
    payment: UserPayment


def create_checkout_session(
    *,
    user: Optional[object] = None,
) -> CheckoutResult:
    """Create a Stripe Checkout Session and persist a pending ``UserPayment``.

    Args:
        user: The Django ``User`` initiating the checkout, or ``None`` for
            anonymous purchases.

    Returns:
        A ``CheckoutResult`` with the Stripe session ID and redirect URL.

    Raises:
        PaymentConfigurationError: When required Stripe settings are empty.
        stripe.error.StripeError: On any Stripe API failure.
    """
    _validate_checkout_config()
    stripe.api_key = settings.STRIPE_SECRET_KEY

    session_kwargs: dict = {
        "payment_method_types": settings.PAYMENT_METHODS,
        "line_items": [
            {
                "price": settings.PRODUCT_PRICE_ID,
                "quantity": 1,
            },
        ],
        "mode": "payment",
        "customer_creation": "always",
        "success_url": settings.REDIRECT_DOMAIN + "/successful?session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": settings.REDIRECT_DOMAIN + "/cancelled",
    }
    if settings.COUPON_ID:
        session_kwargs["discounts"] = [{"coupon": settings.COUPON_ID}]

    checkout_session = stripe.checkout.Session.create(**session_kwargs)

    is_authenticated = user is not None and getattr(user, "is_authenticated", False)
    UserPayment.objects.create(
        app_user=user if is_authenticated else None,
        email=user.email if is_authenticated else None,
        stripe_checkout_id=checkout_session.id,
        payment_bool=False,
    )

    return CheckoutResult(
        session_id=checkout_session.id,
        checkout_url=checkout_session.url,
    )


def confirm_payment(session_id: str, *, host: str = "localhost:8000") -> PaymentConfirmation:
    """Retrieve a completed Stripe session, mark the payment as paid, and
    send a purchase confirmation email.

    Args:
        session_id: The Stripe Checkout Session ID from the success callback.
        host: The request host, used in the email body.

    Returns:
        A ``PaymentConfirmation`` containing the customer email and updated
        ``UserPayment`` record.

    Raises:
        UserPayment.DoesNotExist: If no matching record is found.
        stripe.error.StripeError: On Stripe API failure.
    """
    stripe.api_key = settings.STRIPE_SECRET_KEY

    session = stripe.checkout.Session.retrieve(session_id)
    customer_email: str = session.customer_details.email

    user_payment, _ = UserPayment.objects.update_or_create(
        stripe_checkout_id=session_id,
        defaults={
            "email": customer_email,
            "payment_bool": True,
        },
    )

    _send_purchase_email(customer_email, host=host)

    return PaymentConfirmation(customer_email=customer_email, payment=user_payment)


def handle_webhook_event(payload: bytes, signature: str) -> None:
    """Validate and process a Stripe webhook event.

    Currently handles ``checkout.session.completed`` by marking the
    corresponding ``UserPayment`` as paid.

    Args:
        payload: Raw request body bytes.
        signature: The ``Stripe-Signature`` header value.

    Raises:
        ValueError: If the payload is malformed.
        stripe.error.SignatureVerificationError: If the signature is invalid.
        UserPayment.DoesNotExist: If no matching payment record exists.
    """
    stripe.api_key = settings.STRIPE_SECRET_KEY

    event = stripe.Webhook.construct_event(
        payload, signature, settings.STRIPE_WEBHOOK_SECRET
    )

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        session_id = session.get("id")
        if not session_id:
            raise ValueError("Session ID missing from webhook payload")

        user_payment = UserPayment.objects.get(stripe_checkout_id=session_id)
        user_payment.payment_bool = True
        user_payment.save()
        logger.info("Payment processed for session: %s", session_id)


def get_coupon_info() -> tuple[int, int]:
    """Fetch the current Stripe coupon redemption counts.

    Returns:
        A ``(coupons_left, total_coupons)`` tuple. Returns ``(0, 0)`` when
        the coupon cannot be retrieved.
    """
    try:
        stripe.api_key = settings.STRIPE_SECRET_KEY
        coupon = stripe.Coupon.retrieve(settings.COUPON_ID)
        total: int = coupon.get("max_redemptions", 0)
        left: int = total - coupon.get("times_redeemed", 0)
        return left, total
    except stripe.InvalidRequestError:
        return 0, 0


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _validate_checkout_config() -> None:
    """Ensure required Stripe checkout settings are configured."""
    for setting_name in _CHECKOUT_REQUIRED_SETTINGS:
        if not getattr(settings, setting_name, ""):
            raise PaymentConfigurationError(setting_name, debug=settings.DEBUG)


def _send_purchase_email(email: str, *, host: str = "localhost:8000") -> None:
    """Send a purchase-confirmation email using the JSON template."""
    template_path = os.path.join(
        settings.BASE_DIR, "stripe_payments", "data", "product_bought_email.json"
    )
    with open(template_path) as fh:
        email_data = json.load(fh)

    subject = email_data["subject"]
    message = (
        email_data["message"]
        .replace("{__user_email__}", email)
        .replace("{__url__}", host)
    )

    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=not settings.DEBUG,
    )
