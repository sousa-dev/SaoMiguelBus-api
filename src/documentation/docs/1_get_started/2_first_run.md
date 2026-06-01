# First Run

## Start the Development Server

Always use `run.py` for local development — it runs migrations, installs
Tailwind, and starts both the Django and Tailwind dev servers in one command.

```bash
cd src
python run.py
```

Visit [http://127.0.0.1:8000](http://127.0.0.1:8000).

> **Do not** use `python manage.py runserver` alone unless you only need the
> Django server without Tailwind CSS rebuilding.

## Create an Admin User

Open a second terminal:

```bash
cd src
python manage.py createsuperuser
```

Then visit the admin panel at [http://127.0.0.1:8000/dashboard/admin/](http://127.0.0.1:8000/dashboard/admin/).

## What You'll See

| URL | What it is |
|-----|------------|
| `/` | Dashboard (or landing page if enabled) |
| `/docs/` | This documentation |
| `/accounts/login/` | Login / registration |
| `/dashboard/admin/` | Django admin |

If `AUTHENTICATION_REQUIRED=True` (default), most pages redirect to login.
Public paths are listed in [Auth & OAuth](/docs/configuration/auth_oauth).

## Register a Test User

1. Go to `/accounts/signup/`.
2. Create an account with username + email.
3. Check the terminal — verification emails print to console in dev mode.

## Run Tests

See [Testing](/docs/get_started/testing) for pytest setup, the 80% service-module coverage gate, and conventions.

Quick check:

```bash
cd src
pytest
```

## Next Steps

- [Environment variables](/docs/get_started/environment) — configure OAuth, Stripe, email
- [Feature toggles](/docs/configuration/feature_toggles) — enable/disable apps
- [Deployment](/docs/deployment/) — ship to production
