# djast — Claude Code Configuration

> Instructions for Claude Code agents working in this repository.

## Project Overview

djast is an AI-native Django 5 SaaS boilerplate with pre-configured auth
(allauth + OAuth), Stripe payments, Celery background tasks, Tailwind CSS,
legal pages, markdown documentation, and brute-force protection.

## Agent surfaces

| Surface | Location |
|---------|----------|
| Baseline rules | `.cursor/rules/00-djast-core.mdc` |
| Path personas | `.cursor/rules/*.mdc` |
| Slash commands | `.cursor/commands/` |
| Custom agents | `.cursor/agents/` |
| Architecture | `.agentic/system_architecture.md` |
| Coding standards | `.agentic/coding_standards.md` |
| Cursor entry | `.cursorrules` |

## Slash commands

Claude doesn't native-slash-trigger — prompt: `Run /new-blog-post for topic: X`
and read the matching file in `.cursor/commands/`.

| Category | Commands |
|----------|----------|
| Scaffold | `new-app`, `new-model`, `new-api-endpoint`, `new-task`, `new-periodic-task` |
| Content | `new-blog-post`, `new-free-tool`, `new-doc-page`, `new-legal-page` |
| Config | `new-env-var`, `toggle-app`, `configure-oauth`, `configure-stripe` |
| Workflow | `add-celery-locally`, `deploy-check` |

Full index: `.cursor/commands/README.md`

## Custom agents

Pick in Cursor or prompt: `use djast-backend-engineer` and read `.cursor/agents/djast-backend-engineer.md`.

| Agent | Use for |
|-------|---------|
| `djast-architect` | system design, ADRs |
| `djast-backend-engineer` | models, services, DRF |
| `djast-frontend-engineer` | templates, Tailwind |
| `djast-qa-test-engineer` | pytest, mocks |
| `djast-devops-deployer` | Docker, deployment |
| `djast-seo-content-strategist` | blog/tools SEO |
| `djast-db-migrations-specialist` | migrations |
| `djast-celery-worker-engineer` | Celery tasks |
| `djast-security-reviewer` | auth, secrets |
| `djast-docs-writer` | `/docs/` handbook |
| `djast-code-reviewer` | pre-merge review |

Full index: `.cursor/agents/README.md`

## Essential references

- `src/src/settings.py` — Feature toggles
- `src/src/.env.example` — Environment variables
- `src/blog/AGENT_INSTRUCTIONS.md` — Blog content
- `src/free_tools/AGENT_INSTRUCTIONS.md` — Free tools

## Development commands

```bash
python setup.py              # repo root
cd src && python run.py      # Django + Tailwind
cd src && python manage.py test
celery -A src worker --loglevel=info
celery -A src beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
docker compose up -d
```

## Architecture rules

1. **Service layer** — Logic in `services.py`; views are thin HTTP adapters.
2. **Type hints** — PEP 484; `from __future__ import annotations` in every module.
3. **Docstrings** — Google style on public APIs.
4. **Feature toggles** — `apps` list in `settings.py`.
5. **Explicit > implicit** — Direct service calls over signals for business logic.
6. **Celery** — `@shared_task`, JSON-serializable args, idempotent design.

## Path personas

Read the matching `.cursor/rules/*.mdc` when editing these paths:

| Role | Rule file | Paths |
|------|-----------|-------|
| Models | `models-architect.mdc` | `models.py`, `migrations/`, `admin.py` |
| Services | `service-layer.mdc` | `services.py`, `views.py` |
| API | `api-serializers.mdc` | `api.py`, `serializers.py`, `urls.py` |
| Celery | `celery-tasks.mdc` | `tasks.py`, `agents/`, `management/commands/` |
| Templates | `templates-frontend.mdc` | `templates/`, `theme/`, `static/` |
| Tests | `tests.mdc` | `tests/`, `test_*.py` |
| Settings | `settings-env.mdc` | `settings.py`, `.env*`, Docker |
| Docs | `docs-content.mdc` | `documentation/docs/**/*.md` |
| Blog | `blog-content.mdc` | `src/blog/**` |
| Free tools | `free-tools-content.mdc` | `src/free_tools/**` |

## Documentation maintenance

User-visible changes **must** update `src/documentation/docs/` per
`.agentic/coding_standards.md` §11. Preview: `cd src && python run.py` → `/docs/`.

## Docker (quick ref)

```bash
cp src/src/.env.example src/src/.env
docker compose up -d --build
docker compose exec web python manage.py createsuperuser
```

Services: `db`, `redis`, `web`, `celery-worker`, `celery-beat`.
