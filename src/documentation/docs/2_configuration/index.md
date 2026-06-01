# Configuration

djast centralizes feature control in two places:

1. **`apps` list** in `src/src/settings.py` — enable/disable entire apps
2. **`.env` file** in `src/src/.env` — secrets and environment-specific values

## In This Section

| Page | Topic |
|------|-------|
| [Feature Toggles](/docs/configuration/feature_toggles) | Enable/disable apps from `settings.py` |
| [Auth & OAuth](/docs/configuration/auth_oauth) | Login, OAuth providers, brute-force protection |
| [Stripe](/docs/configuration/stripe) | Payment keys, webhooks, test mode |
| [Email](/docs/configuration/email) | Resend, console, SMTP |
| [Database & Cache](/docs/configuration/database_cache) | SQLite/PostgreSQL, Redis |
| [Analytics](/docs/configuration/analytics) | GA4, Consent Mode, event tracking |

## Quick Reference

```python
# src/src/settings.py
apps = [
    ('allauth.socialaccount.providers.google', True),
    ('allauth.socialaccount.providers.github', True),
    ('admin_interface', True),
    ('rest_framework', True),
    ('axes', True),
    ('landing_page', True),
    ('documentation', True),
    ('app', True),
    ('legal', True),
    ('stripe_payments', True),
    ('blog', True),
    ('free_tools', True),
    ('tailwind', True),
    ('django_browser_reload', False),
]
```

Setting any tuple to `False` removes the app from `INSTALLED_APPS`, its
middleware, and URL routing — no other files need editing.

## Environment File Location

```
src/src/.env          ← your secrets (never commit)
src/src/.env.example  ← documented template
```

Copy the example on first setup:

```bash
cp src/src/.env.example src/src/.env
```

See [Environment](/docs/get_started/environment) for variable details.
