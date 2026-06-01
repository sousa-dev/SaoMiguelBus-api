# Auth & OAuth

djast uses **django-allauth** for authentication with optional Google and
GitHub OAuth. Brute-force protection is handled by **django-axes**.

## Site-Wide Login Gate

Controlled by `AUTHENTICATION_REQUIRED` in `.env` (default `True`).

When enabled, `user_management.middleware.LoginRequiredMiddleware` redirects
unauthenticated users to login — except for these paths:

| Type | Paths |
|------|-------|
| Exact | `/` |
| Prefix | `/media/`, `/login`, `/accounts`, `/payment`, `/legal` |

To make the entire site public, set `AUTHENTICATION_REQUIRED=False` in `.env`.

## Email / Username Settings

| Variable | Default | Effect |
|----------|---------|--------|
| `ACCOUNT_USERNAME_REQUIRED` | `True` | Username required on signup |
| `ACCOUNT_EMAIL_REQUIRED` | `True` | Email required on signup |
| `ACCOUNT_AUTHENTICATION_METHOD` | `username_email` | Login with username or email |
| `ACCOUNT_EMAIL_VERIFICATION` | `optional` | `mandatory`, `optional`, or `none` |

## Google OAuth Setup

1. Create OAuth credentials in [Google Cloud Console](https://console.cloud.google.com/).
2. Set authorized redirect URI: `http://127.0.0.1:8000/accounts/google/login/callback/`
3. Add to `.env`:

```
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_SECRET=your-client-secret
```

4. Ensure `('allauth.socialaccount.providers.google', True)` in `apps` list.

## GitHub OAuth Setup

1. Create an OAuth App in GitHub → Settings → Developer settings.
2. Set callback URL: `http://127.0.0.1:8000/accounts/github/login/callback/`
3. Add to `.env`:

```
GITHUB_CLIENT_ID=your-client-id
GITHUB_SECRET=your-client-secret
```

4. Ensure `('allauth.socialaccount.providers.github', True)` in `apps` list.

## Brute-Force Protection (django-axes)

| Variable | Default | Effect |
|----------|---------|--------|
| `AXES_FAILURE_LIMIT` | `10` | Lock after N failed attempts |
| `AXES_COOLOFF_TIME` | `1` | Lockout hours |
| `AXES_RESET_ON_SUCCESS` | `True` | Reset counter on success |

Disable by setting `('axes', False)` in the `apps` list.

## Key URLs

| URL | Purpose |
|-----|---------|
| `/accounts/login/` | Login |
| `/accounts/signup/` | Registration |
| `/accounts/logout/` | Logout |
| `/accounts/google/login/` | Google OAuth |
| `/accounts/github/login/` | GitHub OAuth |
| `/login/` | Redirect to allauth login |
| `/logout/` | Redirect to allauth logout |

## Troubleshooting

See [Troubleshooting — OAuth](/docs/troubleshooting/) for callback mismatch errors.
