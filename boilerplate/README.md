# [djast](https://djast.dev) — Django Fast. AI-Native. Agent-Ready.

djast is a batteries-included Django 5 SaaS boilerplate designed for rapid
project bootstrapping. Ship authenticated, payment-enabled apps in minutes —
with first-class support for AI coding agents (Cursor, Claude Code, Copilot).

---

## Features

| Category | What you get |
|----------|-------------|
| **Auth** | django-allauth with Google & GitHub OAuth, email verification, brute-force protection (django-axes) |
| **Payments** | Stripe Checkout integration with webhooks, coupon support, purchase emails |
| **Background Tasks** | Celery 5.4 with Redis broker, Celery Beat for periodic tasks, django-celery-beat DB scheduler |
| **UI** | Tailwind CSS 3.4, responsive templates, Font Awesome, dark mode-ready |
| **Legal** | JSON-driven privacy policy, terms of service, and licenses pages |
| **Docs** | Markdown-driven documentation engine with sidebar nav and search |
| **Email** | Resend API (production) / console (development), SMTP fallback |
| **Admin** | Customized Django admin with django-admin-interface |
| **Security** | CSRF, XSS prevention, rate limiting, login middleware |
| **Cache** | Redis-backed Django cache (production), in-memory (development) |
| **Deployment** | docker-compose (web + worker + beat + postgres + redis), Vercel, standalone Docker |
| **AI-Native** | `.cursor/` commands + rules, `.cursorrules`, `CLAUDE.md`, `.agentic/` docs |

---

## Quick Start

### 1. Clone & Setup

```bash
git clone https://github.com/sousa-dev/djast.git
cd djast
python setup.py
```

This creates a `.venv/` virtual environment, installs all dependencies, and runs
initial migrations.

### 2. Configure Environment

```bash
cp src/src/.env.example src/src/.env
```

Edit `src/src/.env` with your secrets. At minimum, set:
- `SECRET_KEY` — generate one at [djast.dev/tools/django-secret-key-generator/](https://djast.dev/tools/django-secret-key-generator/)
- `DEBUG=True` for development

### 3. Run Development Server

```bash
cd src
python run.py
```

This runs migrations, installs Tailwind, and starts both the Django and Tailwind
dev servers. Visit [127.0.0.1:8000](http://127.0.0.1:8000).

> **Always use `run.py`** for local development — it manages the Tailwind
> build pipeline alongside the Django server.

### 4. (Optional) Start Celery for Background Tasks

If you need background task processing during development, start Redis locally
and then in separate terminals:

```bash
# Terminal 1: Celery worker
cd src
celery -A src worker --loglevel=info

# Terminal 2: Celery beat (periodic tasks)
cd src
celery -A src beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

---

## Docker Compose Deployment

The fastest way to deploy the full stack. Five services, one command:

```bash
# 1. Configure
cp src/src/.env.example src/src/.env    # Edit with real values (SECRET_KEY, Stripe keys, etc.)

# 2. Launch
docker compose up -d --build

# 3. Create admin user
docker compose exec web python manage.py createsuperuser
```

### Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| `db` | postgres:16-alpine | 5432 | PostgreSQL database |
| `redis` | redis:7-alpine | 6379 | Celery broker + result backend + Django cache |
| `web` | Dockerfile | 8000 | Django + Gunicorn |
| `celery-worker` | Dockerfile | — | Async task execution |
| `celery-beat` | Dockerfile | — | Periodic task scheduler (django-celery-beat) |

### Useful Commands

```bash
docker compose logs -f web            # Follow web server logs
docker compose logs -f celery-worker  # Follow worker logs
docker compose exec web python manage.py migrate   # Run migrations
docker compose down                   # Stop everything
docker compose down -v                # Stop + remove volumes (wipes data)
```

---

## Project Structure

```
djast/
├── .agentic/              # AI agent orchestration docs
│   ├── system_architecture.md
│   └── coding_standards.md
├── .cursor/               # Slash commands + rules + custom agents
│   ├── commands/          # /new-app, /new-blog-post, ...
│   ├── rules/             # Auto-attach personas by file glob
│   └── agents/            # djast-architect, djast-backend-engineer, ...
├── .cursorrules           # Cursor entry (points to .cursor/)
├── CLAUDE.md              # Claude Code entry (points to .cursor/)
├── Dockerfile             # Production Docker image
├── docker-compose.yml     # Full stack orchestration
├── .env.docker.example    # Docker Compose env template
├── setup.py               # One-shot environment setup
└── src/                   # Django project root
    ├── manage.py
    ├── run.py             # Dev server launcher
    ├── runserver.sh       # Prod launcher (Gunicorn)
    ├── requirements.txt
    ├── src/               # Settings package
    │   ├── __init__.py    # Loads Celery app on startup
    │   ├── celery.py      # Celery app configuration
    │   ├── settings.py    # Feature toggles + config
    │   └── .env.example   # Environment variable docs
    ├── app/               # Your main application
    │   ├── tasks.py       # Celery background tasks
    │   └── ...
    ├── stripe_payments/   # Stripe integration + service layer
    ├── user_management/   # Auth middleware + OAuth signals
    ├── documentation/     # Markdown docs engine
    ├── legal/             # JSON-driven legal pages
    ├── landing_page/      # Optional marketing page
    ├── shared/            # Cross-app email backend + template tags
    └── theme/             # Tailwind CSS compilation
```

---

## Feature Toggles

Enable or disable features by editing the `apps` list in `src/src/settings.py`:

```python
apps = [
    ('allauth.socialaccount.providers.google', True),  # Google OAuth
    ('allauth.socialaccount.providers.github', True),   # GitHub OAuth
    ('admin_interface', True),                          # Custom admin UI
    ('rest_framework', True),                           # DRF API framework
    ('axes', True),                                     # Brute-force protection
    ('landing_page', False),                            # Marketing landing page
    ('documentation', True),                            # Docs engine
    ('app', True),                                      # Main application
    ('legal', True),                                    # Legal pages
    ('stripe_payments', True),                          # Stripe payments
    ('tailwind', True),                                 # Tailwind CSS
    ('django_browser_reload', False),                   # Auto-reload in dev
]
```

Setting any app to `False` removes it from installed apps, middleware, and URL
routing automatically — no need to edit multiple files.

---

## Background Tasks with Celery

### Writing Tasks

Create a `tasks.py` in any Django app:

```python
# app/tasks.py
from celery import shared_task

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_welcome_email(self, *, user_id: int) -> dict:
    """Send a welcome email to a newly registered user."""
    user = User.objects.get(id=user_id)
    send_mail(...)
    return {"status": "sent", "user_id": user_id}
```

### Calling Tasks

```python
# From any view or service
from app.tasks import send_welcome_email
send_welcome_email.delay(user_id=user.id)
```

### Periodic Tasks

Managed via django-celery-beat. Configure schedules through the Django admin
at `/dashboard/admin/` → Periodic Tasks, or programmatically.

---

## Working with AI Agents

djast is designed as an AI-native workspace. When you open this project in
Cursor or Claude Code, the agent automatically reads configuration files that
give it deep context about the architecture, coding standards, and
path-specific expertise.

### Slash commands (vibe-code)

In Cursor, type `/` in chat to run workflows:

| Command | What it does |
|---------|----------------|
| `/new-app` | Scaffold Django app + toggle + docs |
| `/new-model` | Model + migration + admin |
| `/new-api-endpoint` | DRF endpoint via service layer |
| `/new-task` | Celery background task |
| `/new-periodic-task` | Celery Beat schedule |
| `/new-blog-post` | SEO blog post |
| `/new-free-tool` | Free tool page + template |
| `/new-doc-page` | Handbook page at `/docs/` |
| `/new-legal-page` | JSON legal page |
| `/new-env-var` | Env var + settings + docs |
| `/toggle-app` | Enable/disable feature in `settings.py` |
| `/configure-oauth` | Google/GitHub OAuth |
| `/configure-stripe` | Stripe keys + webhooks |
| `/add-celery-locally` | Redis + worker + beat |
| `/deploy-check` | Pre-deploy checklist |

Full index: [`.cursor/commands/README.md`](.cursor/commands/README.md)

Claude Code: prompt `Run /new-blog-post for topic: ...` — it reads the same files.

### Custom agents

Delegatable role workers in [`.cursor/agents/`](.cursor/agents/README.md): `djast-architect`, `djast-backend-engineer`, `djast-frontend-engineer`, `djast-qa-test-engineer`, `djast-devops-deployer`, `djast-seo-content-strategist`, `djast-db-migrations-specialist`, `djast-celery-worker-engineer`, `djast-security-reviewer`, `djast-docs-writer`, `djast-code-reviewer`.

### Path personas (auto-loaded)

Editing matching files loads specialized rules from `.cursor/rules/`:

- **models-architect** — `models.py`, migrations, admin
- **service-layer** — `services.py`, views
- **celery-tasks** — `tasks.py`, management commands
- **blog-content** / **free-tools-content** — content apps

### Entry points

| File | Tool |
|------|------|
| `.cursorrules` | Cursor |
| `CLAUDE.md` | Claude Code |
| `.cursor/rules/00-djast-core.mdc` | Baseline (always on) |

### Agent Orchestration Layer

The `.agentic/` directory contains detailed reference documents:

| File | Purpose |
|------|---------|
| `system_architecture.md` | Tech stack, URL map, auth, Stripe, Celery, deployment, agent surfaces |
| `coding_standards.md` | Patterns, conventions, testing, import order |

App-specific deep dives: `src/blog/AGENT_INSTRUCTIONS.md`, `src/free_tools/AGENT_INSTRUCTIONS.md`

---

## Architecture Conventions

### Service Layer Pattern

Business logic lives in `services.py` files, not in views or models:

```python
# stripe_payments/services.py
def create_checkout_session(*, user=None) -> CheckoutResult:
    """Create a Stripe Checkout Session."""
    ...

# stripe_payments/views.py
def payment(request):
    result = create_checkout_session(user=request.user)
    return redirect(result.checkout_url, code=303)
```

### Type Hints

Every function has PEP 484 type annotations:

```python
from __future__ import annotations

def confirm_payment(session_id: str, *, host: str = "localhost") -> PaymentConfirmation:
    ...
```

---

## Environment Variables

See `src/src/.env.example` for the full list. Key variables:

| Variable | Purpose | Default |
|----------|---------|---------|
| `SECRET_KEY` | Django secret key | — (required) |
| `DEBUG` | Debug mode | `True` |
| `AUTHENTICATION_REQUIRED` | Site-wide login gate | `True` |
| `STRIPE_SECRET_KEY` | Stripe API key | — |
| `RESEND_API_KEY` | Email API key | — |
| `CELERY_BROKER_URL` | Redis URL for Celery | `redis://localhost:6379/0` |
| `REDIS_URL` | Redis URL for Django cache | `redis://localhost:6379/1` |
| `DB_NAME` / `DB_HOST` / ... | PostgreSQL (prod) | — |

---

## Documentation

- **In-app docs**: Run the dev server and visit `/docs/`.
- **Official docs**: [djast.dev/docs](https://djast.dev/docs)
- **Agent docs**: `.agentic/system_architecture.md` and `.agentic/coding_standards.md`.

---

## Contributing

1. Fork the repository.
2. Create a feature branch: `git checkout -b feature/my-feature`.
3. Follow the coding standards in `.agentic/coding_standards.md`.
4. Add tests for new functionality.
5. Submit a pull request.

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).

---

<p align="center">
  Built by <a href="https://x.com/sousadev">@sousadev</a> ·
  <a href="https://djast.dev">djast.dev</a>
</p>
