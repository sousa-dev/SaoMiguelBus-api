# Environment Variables

All secrets and environment-specific config live in `src/src/.env`. Never
commit this file. The template is `src/src/.env.example`.

## Essential Variables (Local Dev)

| Variable | Purpose | Example |
|----------|---------|---------|
| `SECRET_KEY` | Django cryptographic signing | Generate at [/tools/django-secret-key-generator/](/tools/django-secret-key-generator/) |
| `DEBUG` | Debug mode (SQLite, console email, test Stripe keys) | `True` |
| `AUTHENTICATION_REQUIRED` | Site-wide login gate | `True` |

## Analytics (optional)

| Variable | Default | Purpose |
|----------|---------|---------|
| `GOOGLE_ANALYTICS_ID` | *(empty)* | GA4 Measurement ID (`G-...`). Empty = no tracking scripts. |
| `CONSENT_REQUIRED` | `False` | EEA consent banner + Consent Mode v2 default-denied |
| `GA_DEBUG_MODE` | `DEBUG` | GA4 DebugView |

See [Analytics](/docs/configuration/analytics) and [Event Tracking](/docs/customization/event_tracking).

## Auth & Security

| Variable | Default | Purpose |
|----------|---------|---------|
| `ALLOWED_HOSTS` | `127.0.0.1,localhost,...` | Comma-separated hostnames Django accepts |
| `CORS_ALLOWED_ORIGINS` | localhost URLs when `DEBUG=True` | Comma-separated origins (`https://...`) for API CORS |
| `CSRF_TRUSTED_ORIGINS` | same as `CORS_ALLOWED_ORIGINS` | Origins allowed for CSRF-protected POSTs |
| `ACCOUNT_USERNAME_REQUIRED` | `True` | Require username on signup |
| `ACCOUNT_EMAIL_REQUIRED` | `True` | Require email on signup |
| `ACCOUNT_AUTHENTICATION_METHOD` | `username_email` | Login via username or email |
| `ACCOUNT_EMAIL_VERIFICATION` | `optional` | Email verification policy |
| `AXES_FAILURE_LIMIT` | `10` | Failed login attempts before lockout |
| `AXES_COOLOFF_TIME` | `1` | Lockout duration (hours) |
| `AXES_RESET_ON_SUCCESS` | `True` | Reset counter on successful login |

## OAuth (Optional for Local Dev)

| Variable | Purpose |
|----------|---------|
| `GOOGLE_CLIENT_ID` / `GOOGLE_SECRET` | Google OAuth |
| `GITHUB_CLIENT_ID` / `GITHUB_SECRET` | GitHub OAuth |

See [Auth & OAuth](/docs/configuration/auth_oauth) for provider setup.

## Stripe (Optional for Local Dev)

When `DEBUG=True`, djast uses `TEST_*` prefixed keys automatically:

| Variable | Purpose |
|----------|---------|
| `TEST_STRIPE_PUBLIC_KEY` | Stripe publishable key (test mode) |
| `TEST_STRIPE_SECRET_KEY` | Stripe secret key (test mode) |
| `TEST_STRIPE_WEBHOOK_SECRET` | Webhook signing secret (test mode) |
| `TEST_PRODUCT_PRICE_ID` | Stripe Price ID for checkout |
| `TEST_REDIRECT_DOMAIN` | Base URL for payment redirects |

See [Stripe](/docs/configuration/stripe) for full setup.

## Email

| Variable | Purpose |
|----------|---------|
| `RESEND_API_KEY` | Resend API key (production) |
| `DEFAULT_FROM_EMAIL` | Sender address |

In dev (`DEBUG=True`), emails print to the console — no API key needed.

## Database & Cache (Production)

| Variable | Purpose |
|----------|---------|
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | PostgreSQL (when `DEBUG=False`) |
| `REDIS_URL` | Redis cache backend (leave empty for in-memory cache in dev) |
| `CELERY_BROKER_URL` | Celery message broker |
| `CELERY_RESULT_BACKEND` | Celery result store |

See [Database & Cache](/docs/configuration/database_cache).

## Adding New Variables

When you add a new env var to `settings.py`:

1. Add it to `src/src/.env.example` with a comment.
2. Update this page or the relevant [Configuration](/docs/configuration/) page.
3. If production-only, also update [Production Environment](/docs/deployment/production_env).

This is required for both human developers and AI agents — see
[Maintaining Docs](/docs/maintaining_docs/).
