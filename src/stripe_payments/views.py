"""Stripe payment views.

Thin request-handling layer that delegates all business logic to
``stripe_payments.services``.
"""

from __future__ import annotations

import logging

import stripe
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt

from stripe_payments.exceptions import PaymentConfigurationError
from stripe_payments.services import (
    confirm_payment,
    create_checkout_session,
    handle_webhook_event,
)

logger = logging.getLogger(__name__)


def payment(request: HttpRequest) -> HttpResponse:
    """Initiate a Stripe Checkout session and redirect the user."""
    try:
        result = create_checkout_session(user=request.user)
    except PaymentConfigurationError:
        logger.exception("Stripe checkout misconfigured")
        return HttpResponse(
            "Payment is temporarily unavailable. Please try again later.",
            status=503,
        )
    return redirect(result.checkout_url, code=303)


def success(request: HttpRequest) -> HttpResponse:
    """Handle the post-checkout success redirect from Stripe."""
    checkout_session_id = request.GET.get("session_id")
    if checkout_session_id is None:
        return HttpResponse(status=400)

    try:
        confirmation = confirm_payment(checkout_session_id, host=request.get_host())
        return render(
            request,
            "stripe_payments/success.html",
            {
                "customer_email": confirmation.customer_email,
                "session_id": checkout_session_id,
            },
        )
    except Exception:
        logger.exception("Error processing payment success for session %s", checkout_session_id)
        return HttpResponse(status=500)


def cancel(request: HttpRequest) -> HttpResponse:
    """Render the payment-cancelled page."""
    return render(request, "stripe_payments/cancelled.html")


@csrf_exempt
def stripe_webhook(request: HttpRequest) -> HttpResponse:
    """Receive and validate Stripe webhook events."""
    try:
        handle_webhook_event(
            payload=request.body,
            signature=request.META["HTTP_STRIPE_SIGNATURE"],
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        logger.exception("Webhook signature verification failed")
        return HttpResponse(status=400)
    except Exception:
        logger.exception("Webhook processing error")
        return HttpResponse(status=500)

    return HttpResponse(status=200)
