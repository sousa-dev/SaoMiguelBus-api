# User Management

Auth wrappers, login middleware, and OAuth signal handlers.

## What It Provides

| Component | File | Purpose |
|-----------|------|---------|
| Login gate | `middleware.py` | Redirects unauthenticated users |
| OAuth signals | `signals.py` | Populates email from GitHub OAuth |
| Login/logout | `views.py` | Redirects to allauth views |
| Templates | `templates/allauth/` | Custom allauth layout |

## Login Gate

`LoginRequiredMiddleware` runs when `AUTHENTICATION_REQUIRED=True`.

**Public paths** (no login required):

- `/` (exact)
- `/media/`, `/login`, `/accounts`, `/payment`, `/legal` (prefix match)

To change exclusions, edit `user_management/middleware.py` and update
[Auth & OAuth](/docs/configuration/auth_oauth).

## Key URLs

| URL | Handler |
|-----|---------|
| `/login/` | Redirect to allauth login |
| `/logout/` | Redirect to allauth logout |

Allauth handles `/accounts/*` directly.

## Always Active

User management is loaded when `AUTHENTICATION_REQUIRED=True` — it is not in
the `apps` toggle list but depends on the env var.

See [Auth & OAuth](/docs/configuration/auth_oauth) for OAuth and axes config.
