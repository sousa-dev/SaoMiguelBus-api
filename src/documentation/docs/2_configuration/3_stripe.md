# Stripe

djast integrates Stripe Checkout with webhooks and a service layer in
`stripe_payments/services.py`.

## Payment Flow

1. User visits `/payment/pay/` → Stripe Checkout Session created.
2. User completes payment on Stripe's hosted page.
3. Success redirect to `/payment/successful/?session_id=...` → payment confirmed.
4. Webhook at `/payment/webhook/` → backup confirmation path.

## Environment Variables

When `DEBUG=True`, djast automatically uses `TEST_*` prefixed keys.

### Test Mode (`DEBUG=True`)

| Variable | Purpose |
|----------|---------|
| `TEST_STRIPE_PUBLIC_KEY` | Publishable key |
| `TEST_STRIPE_SECRET_KEY` | Secret key |
| `TEST_STRIPE_WEBHOOK_SECRET` | Webhook signing secret |
| `TEST_PRODUCT_PRICE_ID` | Stripe Price ID |
| `TEST_COUPON_ID` | Optional coupon ID |
| `TEST_REDIRECT_DOMAIN` | e.g. `http://127.0.0.1:8000/payment` |

### Production (`DEBUG=False`)

| Variable | Purpose |
|----------|---------|
| `STRIPE_PUBLIC_KEY` | Publishable key |
| `STRIPE_SECRET_KEY` | Secret key |
| `STRIPE_WEBHOOK_SECRET` | Webhook signing secret |
| `PRODUCT_PRICE_ID` | Stripe Price ID |
| `COUPON_ID` | Optional coupon ID |
| `REDIRECT_DOMAIN` | e.g. `https://yourdomain.com/payment` |

### Shared

| Variable | Default | Purpose |
|----------|---------|---------|
| `PAYMENT_METHODS` | `card,link` | Comma-separated payment methods |

## Webhook Setup

1. In Stripe Dashboard → Developers → Webhooks, add endpoint:
   - Local: use [Stripe CLI](https://stripe.com/docs/stripe-cli) to forward events
   - Production: `https://yourdomain.com/payment/webhook/`
2. Copy the signing secret to `TEST_STRIPE_WEBHOOK_SECRET` or `STRIPE_WEBHOOK_SECRET`.
3. Listen for `checkout.session.completed` events.

### Local Testing with Stripe CLI

```bash
stripe listen --forward-to localhost:8000/payment/webhook/
```

Copy the webhook signing secret it prints to your `.env`.

## Key URLs

| URL | Purpose |
|-----|---------|
| `/payment/pay/` | Initiate checkout |
| `/payment/successful/` | Post-payment success page |
| `/payment/cancelled/` | User cancelled checkout |
| `/payment/webhook/` | Stripe webhook receiver |

## Admin

Payment records appear in Django admin under **User Payments**.

See [Stripe Payments app](/docs/apps/stripe_payments) for implementation details.
