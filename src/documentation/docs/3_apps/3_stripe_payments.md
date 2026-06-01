# Stripe Payments

Pre-configured Stripe Checkout integration with webhooks and email receipts.

## URLs

| Path | Purpose |
|------|---------|
| `/payment/pay/` | Initiate Stripe Checkout |
| `/payment/successful/` | Post-payment success page |
| `/payment/cancelled/` | User cancelled checkout |
| `/payment/webhook/` | Stripe webhook receiver |

## Architecture

Business logic lives in `stripe_payments/services.py`:

| Function | Purpose |
|----------|---------|
| `create_checkout_session()` | Creates Stripe session + pending `UserPayment` |
| `confirm_payment()` | Marks payment paid, sends receipt email |
| `handle_webhook_event()` | Validates webhook signature, confirms payment |

Views in `stripe_payments/views.py` are thin HTTP adapters.

## Configuration

See [Stripe Configuration](/docs/configuration/stripe) for env vars and webhook setup.

## Admin

View payment records at `/dashboard/admin/` → **User Payments**.

## Enable / Disable

```python
('stripe_payments', True),  # src/src/settings.py
```

Payment paths (`/payment/`) are excluded from the login gate so unauthenticated
users can complete checkout.
