# Getting Started

djast is a batteries-included Django 5 SaaS boilerplate. This section gets you
from zero to a running app in under five minutes.

## Prerequisites

| Requirement | Version |
|-------------|---------|
| Python | 3.10+ |
| Git | any recent version |
| Node.js | 18+ (used by Tailwind build) |
| Redis | optional — only needed for Celery/background tasks |

## 60-Second Tour

1. **Clone & setup** — `python setup.py` creates a venv and runs migrations.
2. **Configure** — copy `src/src/.env.example` → `src/src/.env`.
3. **Run** — `cd src && python run.py` starts Django + Tailwind.
4. **Browse** — open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## In This Section

| Page | What you'll learn |
|------|-------------------|
| [Install](/docs/get_started/install) | Clone the repo and run the setup script |
| [First Run](/docs/get_started/first_run) | Start the dev server and create an admin user |
| [Environment](/docs/get_started/environment) | Essential `.env` variables for local development |
| [AI Agents](/docs/get_started/ai_agents) | Cursor slash commands, rules, and `djast-*` agents |
| [Testing](/docs/get_started/testing) | pytest, coverage gate on service modules |

## What's Included Out of the Box

| Feature | Default | Docs |
|---------|---------|------|
| Authentication (allauth) | On | [Auth & OAuth](/docs/configuration/auth_oauth) |
| Google / GitHub OAuth | On | [Auth & OAuth](/docs/configuration/auth_oauth) |
| Stripe Payments | On | [Stripe](/docs/configuration/stripe) |
| Documentation engine | On | [Documentation app](/docs/apps/documentation) |
| Blog | On | [Blog](/docs/apps/blog) |
| Free Tools | On | [Free Tools](/docs/apps/free_tools) |
| Legal pages | On | [Legal](/docs/apps/legal) |
| Tailwind CSS | On | [Tailwind theme](/docs/customization/tailwind_theme) |
| Celery + Redis | Configured | [Background Tasks](/docs/background_tasks/) |
| Brute-force protection | On | [Auth & OAuth](/docs/configuration/auth_oauth) |

All features are toggled from the `apps` list in `src/src/settings.py`. See
[Feature Toggles](/docs/configuration/feature_toggles) for details.

## Next Steps

After your first run:

- Vibe-code with Cursor → [AI Agents, Rules & Commands](/docs/get_started/ai_agents)
- Configure OAuth and Stripe keys in `.env` → [Configuration](/docs/configuration/)
- Deploy with Docker Compose → [Deployment](/docs/deployment/)
- Customize the UI → [Customization](/docs/customization/)
