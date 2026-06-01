# Directory Layout

Annotated project tree.

```
djast/                              # Repo root
├── .agentic/                       # Agent orchestration docs
│   ├── system_architecture.md      # Tech stack, URL map, deployment
│   └── coding_standards.md         # Patterns, testing, conventions
├── .cursor/                        # Cursor vibe-code layer
│   ├── commands/                   # Slash commands (/new-app, …)
│   ├── rules/                      # Auto-attach personas (*.mdc)
│   └── agents/                     # Custom agents (djast-*)
├── .cursorrules                    # Cursor entry (pointers)
├── CLAUDE.md                       # Claude Code entry (pointers)
├── Dockerfile                      # Production Docker image
├── docker-compose.yml              # Full stack orchestration
├── setup.py                        # One-shot env setup
└── src/                            # Django project root (run commands here)
    ├── manage.py
    ├── run.py                      # Dev launcher (Django + Tailwind)
    ├── runserver.sh                # Prod launcher (Gunicorn)
    ├── requirements.txt
    ├── vercel.json                 # Vercel deployment config
    ├── context_processors.py       # Template context (project name, GA)
    ├── src/                        # Settings package
    │   ├── __init__.py             # Loads Celery app on startup
    │   ├── celery.py               # Celery configuration
    │   ├── settings.py             # Feature toggles + all config
    │   ├── urls.py                 # Root URL dispatcher
    │   ├── wsgi.py / asgi.py
    │   └── .env.example            # Environment variable template
    ├── app/                        # Main application
    │   ├── models.py
    │   ├── serializers.py
    │   ├── tasks.py                # Celery background tasks
    │   ├── urls.py
    │   ├── views/
    │   ├── templates/app/
    │   └── tests/
    ├── stripe_payments/            # Stripe integration
    │   ├── models.py               # UserPayment
    │   ├── services.py             # Payment business logic
    │   ├── views.py                # Thin HTTP handlers
    │   └── templates/
    ├── user_management/            # Auth wrappers
    │   ├── middleware.py           # LoginRequiredMiddleware
    │   ├── signals.py              # OAuth email population
    │   └── templates/allauth/
    ├── documentation/              # This docs engine
    │   ├── views.py
    │   ├── docs/                   # Markdown content (you are here)
    │   └── templates/
    ├── blog/                       # SEO blog
    │   ├── models.py
    │   ├── services.py
    │   ├── AGENT_INSTRUCTIONS.md
    │   └── templates/
    ├── free_tools/                 # Free tool pages
    │   ├── models.py
    │   ├── services.py
    │   ├── AGENT_INSTRUCTIONS.md
    │   └── templates/
    ├── legal/                      # Legal pages
    │   ├── views.py
    │   └── data/                   # JSON content files
    ├── landing_page/               # Marketing page (optional)
    ├── shared/                     # Cross-app utilities
    │   ├── resend_backend.py       # Resend email backend
    │   └── templatetags/
    └── theme/                      # Tailwind CSS compilation
        └── static_src/
            └── tailwind.config.js
```

## Key Conventions

| Pattern | Location |
|---------|----------|
| Business logic | `<app>/services.py` |
| Background tasks | `<app>/tasks.py` |
| Feature toggles | `src/src/settings.py` `apps` list |
| Secrets | `src/src/.env` |
| Human docs | `documentation/docs/` |
| Agent docs | `.agentic/`, `.cursor/`, `CLAUDE.md`, `.cursorrules` |
| Human agent guide | `/docs/get_started/ai_agents` |

## Run Commands From

Always run Django management commands from `src/`:

```bash
cd src
python manage.py <command>
python run.py          # dev server
celery -A src worker   # Celery worker
```

Setup script runs from repo root:

```bash
python setup.py        # from djast/
```
