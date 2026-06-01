# Feature Toggles

Every optional feature in djast is controlled by the `apps` list at the top of
`src/src/settings.py`.

## How It Works

```python
apps = [
    ('app_name', True),   # enabled
    ('other_app', False), # disabled
]
```

When an app is `False`:

- It is **not** added to `INSTALLED_APPS`.
- Its URL patterns are **not** registered.
- App-specific middleware is **not** loaded.
- App-specific settings functions are **not** called.

## Available Toggles

| App | What it enables |
|-----|-----------------|
| `allauth.socialaccount.providers.google` | Google OAuth login |
| `allauth.socialaccount.providers.github` | GitHub OAuth login |
| `admin_interface` | Custom Django admin UI |
| `rest_framework` | DRF API framework |
| `axes` | Brute-force login protection |
| `landing_page` | Marketing landing page at `/` |
| `documentation` | This docs site at `/docs/` |
| `app` | Main dashboard application |
| `legal` | Privacy policy, terms, licenses |
| `stripe_payments` | Stripe Checkout integration |
| `blog` | SEO blog at `/blog/` |
| `free_tools` | Free tools at `/tools/` |
| `tailwind` | Tailwind CSS compilation |
| `django_browser_reload` | Auto browser reload in dev |

## Dependencies

| Rule | Reason |
|------|--------|
| `landing_page` requires `app` | Landing page links to `/app/` dashboard |
| OAuth providers require `AUTHENTICATION_REQUIRED=True` | Social login needs allauth |

## Common Configurations

### SaaS Dashboard (default)

```python
('landing_page', False),  # Dashboard at /
('app', True),
```

### Marketing Site + App

```python
('landing_page', True),   # Landing at /
('app', True),            # Dashboard at /app/
```

### Minimal (auth + dashboard only)

```python
('documentation', False),
('legal', False),
('stripe_payments', False),
('blog', False),
('free_tools', False),
('landing_page', False),
```

After changing toggles, restart the dev server.

## Per-App Documentation

See [Built-in Apps](/docs/apps/) for what each app provides when enabled.
