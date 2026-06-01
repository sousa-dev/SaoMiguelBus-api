"""Tests for stripe_payments.services."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import stripe
from django.contrib.auth.models import User
from django.test import override_settings

from stripe_payments.models import UserPayment
from stripe_payments.exceptions import PaymentConfigurationError
from stripe_payments.services import (
    confirm_payment,
    create_checkout_session,
    get_coupon_info,
    handle_webhook_event,
)

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
def user(db: None) -> User:
    """Authenticated user for checkout tests."""
    return User.objects.create_user(
        username="buyer",
        email="buyer@example.com",
        password="testpass123",
    )


@override_settings(**STRIPE_SETTINGS)
@pytest.mark.django_db
@patch("stripe_payments.services.stripe.checkout.Session.create")
def test_create_checkout_session_authenticated_user(
    mock_create: MagicMock,
    user: User,
) -> None:
    """Happy path: authenticated user gets checkout URL and pending payment."""
    mock_create.return_value = MagicMock(
        id="cs_test_auth",
        url="https://checkout.stripe.com/auth",
    )

    result = create_checkout_session(user=user)

    assert result.session_id == "cs_test_auth"
    assert result.checkout_url == "https://checkout.stripe.com/auth"
    payment = UserPayment.objects.get(stripe_checkout_id="cs_test_auth")
    assert payment.payment_bool is False
    assert payment.app_user == user
    assert payment.email == "buyer@example.com"


@override_settings(**STRIPE_SETTINGS)
@pytest.mark.django_db
@patch("stripe_payments.services.stripe.checkout.Session.create")
def test_create_checkout_session_anonymous(mock_create: MagicMock) -> None:
    """Happy path: anonymous checkout persists payment without app_user."""
    mock_create.return_value = MagicMock(
        id="cs_test_anon",
        url="https://checkout.stripe.com/anon",
    )

    result = create_checkout_session(user=None)

    assert result.session_id == "cs_test_anon"
    payment = UserPayment.objects.get(stripe_checkout_id="cs_test_anon")
    assert payment.app_user is None
    assert payment.email is None


@override_settings(**{**STRIPE_SETTINGS, "PRODUCT_PRICE_ID": ""})
@pytest.mark.django_db
@patch("stripe_payments.services.stripe.checkout.Session.create")
def test_create_checkout_session_empty_price_raises(
    mock_create: MagicMock,
) -> None:
    """Error path: empty PRODUCT_PRICE_ID raises before Stripe API call."""
    with pytest.raises(PaymentConfigurationError, match="PRODUCT_PRICE_ID"):
        create_checkout_session(user=None)

    mock_create.assert_not_called()


@override_settings(**{**STRIPE_SETTINGS, "COUPON_ID": ""})
@pytest.mark.django_db
@patch("stripe_payments.services.stripe.checkout.Session.create")
def test_create_checkout_session_omits_discounts_without_coupon(
    mock_create: MagicMock,
) -> None:
    """Edge case: empty COUPON_ID omits discounts from checkout session."""
    mock_create.return_value = MagicMock(
        id="cs_no_coupon",
        url="https://checkout.stripe.com/no-coupon",
    )

    create_checkout_session(user=None)

    _, kwargs = mock_create.call_args
    assert "discounts" not in kwargs


@override_settings(**STRIPE_SETTINGS)
@pytest.mark.django_db
@patch("stripe_payments.services.stripe.checkout.Session.create")
def test_create_checkout_session_includes_discounts_with_coupon(
    mock_create: MagicMock,
) -> None:
    """Happy path: configured COUPON_ID is passed to Stripe."""
    mock_create.return_value = MagicMock(
        id="cs_with_coupon",
        url="https://checkout.stripe.com/with-coupon",
    )

    create_checkout_session(user=None)

    _, kwargs = mock_create.call_args
    assert kwargs["discounts"] == [{"coupon": "coupon_test_fake"}]


@override_settings(**STRIPE_SETTINGS)
@pytest.mark.django_db
@patch("stripe_payments.services.send_mail")
@patch("stripe_payments.services.stripe.checkout.Session.retrieve")
def test_confirm_payment_marks_paid_and_sends_email(
    mock_retrieve: MagicMock,
    mock_send_mail: MagicMock,
) -> None:
    """Happy path: confirm_payment updates record and sends purchase email."""
    UserPayment.objects.create(
        stripe_checkout_id="cs_confirm",
        payment_bool=False,
    )
    mock_retrieve.return_value = MagicMock(
        customer_details=MagicMock(email="customer@example.com"),
    )

    result = confirm_payment("cs_confirm", host="example.com")

    assert result.customer_email == "customer@example.com"
    assert result.payment.payment_bool is True
    mock_send_mail.assert_called_once()


@override_settings(**STRIPE_SETTINGS)
@pytest.mark.django_db
@patch("stripe_payments.services.stripe.Webhook.construct_event")
def test_handle_webhook_event_marks_payment_paid(
    mock_construct: MagicMock,
) -> None:
    """Happy path: checkout.session.completed marks UserPayment as paid."""
    payment = UserPayment.objects.create(
        stripe_checkout_id="cs_webhook",
        payment_bool=False,
    )
    mock_construct.return_value = {
        "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_webhook"}},
    }

    handle_webhook_event(b"payload", "sig_header")

    payment.refresh_from_db()
    assert payment.payment_bool is True


@override_settings(**STRIPE_SETTINGS)
@patch("stripe_payments.services.stripe.Coupon.retrieve")
def test_get_coupon_info_returns_remaining(mock_retrieve: MagicMock) -> None:
    """Happy path: coupon info returns (left, total) tuple."""
    mock_retrieve.return_value = {
        "max_redemptions": 100,
        "times_redeemed": 30,
    }

    left, total = get_coupon_info()

    assert left == 70
    assert total == 100


@override_settings(**STRIPE_SETTINGS)
@patch("stripe_payments.services.stripe.Coupon.retrieve")
def test_get_coupon_info_invalid_request_returns_zeros(
    mock_retrieve: MagicMock,
) -> None:
    """Edge case: invalid coupon returns (0, 0)."""
    mock_retrieve.side_effect = stripe.InvalidRequestError(
        "No such coupon",
        param="id",
    )

    left, total = get_coupon_info()

    assert left == 0
    assert total == 0


@override_settings(**STRIPE_SETTINGS)
@patch("stripe_payments.services.stripe.Webhook.construct_event")
def test_handle_webhook_event_missing_session_id_raises(
    mock_construct: MagicMock,
) -> None:
    """Error path: missing session id in payload raises ValueError."""
    mock_construct.return_value = {
        "type": "checkout.session.completed",
        "data": {"object": {}},
    }

    with pytest.raises(ValueError, match="Session ID missing"):
        handle_webhook_event(b"payload", "sig_header")


@override_settings(**STRIPE_SETTINGS)
@pytest.mark.django_db
@patch("stripe_payments.services.stripe.Webhook.construct_event")
def test_handle_webhook_event_missing_payment_raises(
    mock_construct: MagicMock,
) -> None:
    """Error path: unknown session id raises UserPayment.DoesNotExist."""
    mock_construct.return_value = {
        "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_unknown"}},
    }

    with pytest.raises(UserPayment.DoesNotExist):
        handle_webhook_event(b"payload", "sig_header")


@override_settings(**STRIPE_SETTINGS)
@patch("stripe_payments.services.stripe.Webhook.construct_event")
def test_handle_webhook_event_invalid_signature_raises(
    mock_construct: MagicMock,
) -> None:
    """Error path: invalid signature propagates SignatureVerificationError."""
    mock_construct.side_effect = stripe.error.SignatureVerificationError(
        "Invalid signature",
        sig_header="bad",
    )

    with pytest.raises(stripe.error.SignatureVerificationError):
        handle_webhook_event(b"payload", "bad_sig")
