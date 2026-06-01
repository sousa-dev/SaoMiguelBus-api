# Production Environment

Required environment variables and settings for production deployment.

## Critical Settings

| Variable | Value | Why |
|----------|-------|-----|
| `DEBUG` | `False` | Enables PostgreSQL, production Stripe keys, Resend email |
| `SECRET_KEY` | Strong random string | Cryptographic signing — never use default |
| `ALLOWED_HOSTS` | Your domain(s) | Comma-separated, e.g. `djast.dev,www.djast.dev` |
| `CORS_ALLOWED_ORIGINS` | Your site URL(s) | Comma-separated with scheme, e.g. `https://djast.dev` |
| `CSRF_TRUSTED_ORIGINS` | Same as CORS (optional) | Override if CSRF origins differ from CORS |

## Database (Required)

```env
DB_NAME=postgres
DB_USER=your_user
DB_PASSWORD=your_password
DB_HOST=your_host
DB_PORT=5432
```

## Stripe (Production Keys)

When `DEBUG=False`, djast uses non-prefixed keys:

```env
STRIPE_PUBLIC_KEY=pk_live_...
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
PRODUCT_PRICE_ID=price_...
REDIRECT_DOMAIN=https://yourdomain.com/payment
```

### Staging with test Stripe keys

Staging environments typically run with `DEBUG=False` (PostgreSQL, production
email path) but may still use Stripe **test-mode** credentials. That is fine —
but you must use **unprefixed** variable names (`PRODUCT_PRICE_ID`, not
`TEST_PRODUCT_PRICE_ID`). Copy values from your local `TEST_*` vars into the
unprefixed names on the staging host.

Verify configuration before deploy:

```bash
cd src
python manage.py check --deploy
```

## Analytics

```env
GOOGLE_ANALYTICS_ID=G-XXXXXXXXXX
CONSENT_REQUIRED=True
GA_DEBUG_MODE=False
```

Set `CONSENT_REQUIRED=True` for EEA traffic. Register custom dimensions in GA4
(`page_type`, `post_slug`, `tool_slug`, `plan`). See
[Analytics](/docs/configuration/analytics).

## Email

```env
RESEND_API_KEY=re_...
DEFAULT_FROM_EMAIL=noreply@yourdomain.com
```

## Redis & Celery

```env
CELERY_BROKER_URL=redis://your-redis:6379/0
CELERY_RESULT_BACKEND=redis://your-redis:6379/0
REDIS_URL=redis://your-redis:6379/1
```

## OAuth

Update redirect URIs in Google/GitHub console to production domain:

```
https://yourdomain.com/accounts/google/login/callback/
https://yourdomain.com/accounts/github/login/callback/
```

## Security Checklist

- [ ] `DEBUG=False`
- [ ] Unique `SECRET_KEY` (not `YOUR_SECRET_KEY_HERE`)
- [ ] `ALLOWED_HOSTS` includes your domain
- [ ] HTTPS enforced (via reverse proxy or platform)
- [ ] Production Stripe webhook configured
- [ ] OAuth callback URLs updated
- [ ] `AUTHENTICATION_REQUIRED=True` (unless intentionally public)
- [ ] Admin URL not publicly advertised (`/dashboard/admin/`)

## Deploy Steps

```bash
cd src
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

In Docker Compose, run via `docker compose exec web`.

## Adding New Production Variables

When adding env vars to `settings.py`:

1. Document in `src/src/.env.example`
2. Update this page
3. Document in `src/src/.env.example` if needed (Docker services use `env_file`, not hardcoded compose overrides)

See [Maintaining Docs](/docs/maintaining_docs/).
