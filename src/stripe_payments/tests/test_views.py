"""Tests for stripe_payments.views."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings
from django.urls import reverse

from stripe_payments.exceptions import PaymentConfigurationError

STRIPE_SETTINGS = {
    "STRIPE_SECRET_KEY": "sk_test_fake",
    "STRIPE_PUBLIC_KEY": "pk_test_fake",
    "STRIPE_WEBHOOK_SECRET": "whsec_test_fake",
    "PRODUCT_PRICE_ID": "price_test_fake",
    "COUPON_ID": "coupon_test_fake",
    "REDIRECT_DOMAIN": "http://localhost:8000",
    "PAYMENT_METHODS": ["card"],
    "DEFAULT_FROM_EMAIL": "noreply@example.com",
    "DEBUG": True,
}


@pytest.fixture
def client() -> Client:
    """Django test client."""
    return Client()


@pytest.fixture
def user(db: None) -> User:
    """Authenticated user for payment view tests."""
    return User.objects.create_user(
        username="buyer",
        email="buyer@example.com",
        password="testpass123",
    )


@override_settings(**STRIPE_SETTINGS)
@pytest.mark.django_db
@patch("stripe_payments.views.create_checkout_session")
def test_payment_view_redirects_on_success(
    mock_create: MagicMock,
    client: Client,
    user: User,
) -> None:
    """Happy path: payment view redirects to Stripe checkout URL."""
    from stripe_payments.services import CheckoutResult

    client.force_login(user)
    mock_create.return_value = CheckoutResult(
        session_id="cs_view",
        checkout_url="https://checkout.stripe.com/view",
    )

    response = client.post(reverse("payment"))

    assert response.status_code in (302, 303)
    assert response["Location"] == "https://checkout.stripe.com/view"


@override_settings(**STRIPE_SETTINGS)
@pytest.mark.django_db
@patch("stripe_payments.views.create_checkout_session")
def test_payment_view_returns_503_on_misconfiguration(
    mock_create: MagicMock,
    client: Client,
    user: User,
) -> None:
    """Error path: misconfigured Stripe settings return 503."""
    client.force_login(user)
    mock_create.side_effect = PaymentConfigurationError(
        "PRODUCT_PRICE_ID",
        debug=False,
    )

    response = client.post(reverse("payment"))

    assert response.status_code == 503
    assert b"temporarily unavailable" in response.content
