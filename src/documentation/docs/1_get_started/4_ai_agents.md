# AI Agents, Rules & Commands

djast is built for **vibe-coding** with Cursor, Claude Code, and other AI assistants.
This page explains the three agent surfaces in the repo and how to use them.

## Three layers

| Layer | Location | How it activates |
|-------|----------|------------------|
| **Rules** | `.cursor/rules/*.mdc` | **Automatic** — Cursor loads matching rules when you edit files (e.g. `services.py` → service-layer persona) |
| **Commands** | `.cursor/commands/*.md` | **You invoke** — type `/` in Cursor chat (e.g. `/new-blog-post`) |
| **Custom agents** | `.cursor/agents/djast-*.md` | **You invoke** — pick from the agent menu or prompt `use djast-backend-engineer` |

Rules add context. Commands are step-by-step recipes. Custom agents are full-role workers for bigger tasks.

> Rules and the core baseline attach automatically. Commands and `djast-*` agents do **not** switch on their own — you run them or ask the chat to follow them.

## Slash commands

In **Cursor**, type `/` in chat and choose a command (or name it in your prompt).

### Scaffolding

| Command | Purpose |
|---------|---------|
| `/new-app` | Scaffold Django app + feature toggle + docs |
| `/new-model` | Model, migration, admin, tests |
| `/new-api-endpoint` | DRF endpoint via service layer |
| `/new-task` | Celery background task |
| `/new-periodic-task` | Celery Beat schedule |

### Content

| Command | Purpose |
|---------|---------|
| `/new-blog-post` | SEO blog post |
| `/new-free-tool` | Free tool template + DB record |
| `/new-doc-page` | New handbook page at `/docs/` |
| `/new-legal-page` | JSON legal page |

### Configuration

| Command | Purpose |
|---------|---------|
| `/new-env-var` | Env var + settings + docs |
| `/toggle-app` | Enable/disable app in `settings.py` |
| `/configure-oauth` | Google/GitHub OAuth |
| `/configure-stripe` | Stripe keys + webhooks |

### Workflow

| Command | Purpose |
|---------|---------|
| `/add-celery-locally` | Redis + Celery worker + beat |
| `/deploy-check` | Pre-deploy checklist |

Source files live in `.cursor/commands/`. Full list: `.cursor/commands/README.md` in the repo.

### Claude Code

Claude does not slash-trigger natively. Prompt instead:

```
Run /new-blog-post for topic: reducing SaaS churn
```

The assistant reads the matching file under `.cursor/commands/`.

## Path personas (rules)

While you edit code, Cursor auto-attaches rules from `.cursor/rules/`:

| Rule | Activates when you edit |
|------|-------------------------|
| `00-djast-core` | Always on (baseline conventions) |
| `models-architect` | `models.py`, `migrations/`, `admin.py` |
| `service-layer` | `services.py`, `views.py` |
| `api-serializers` | `api.py`, `serializers.py`, `urls.py` |
| `celery-tasks` | `tasks.py`, `management/commands/` |
| `templates-frontend` | `templates/`, `theme/`, `static/` |
| `tests` | `tests/`, `test_*.py` |
| `settings-env` | `settings.py`, `.env*`, Docker files |
| `docs-content` | `documentation/docs/**/*.md` |
| `blog-content` | `src/blog/**` |
| `free-tools-content` | `src/free_tools/**` |

## Custom agents (`djast-*`)

Pick a specialized agent in Cursor's agent menu, or say e.g. **"use djast-backend-engineer"** for server-side work.

| Agent | Use for |
|-------|---------|
| `djast-architect` | System design, ADRs, cross-app features |
| `djast-backend-engineer` | Models, services, views, DRF |
| `djast-frontend-engineer` | Templates, Tailwind, landing page |
| `djast-qa-test-engineer` | pytest, mocks, coverage |
| `djast-devops-deployer` | Docker, deployment, prod env |
| `djast-seo-content-strategist` | Blog, free tools, SEO |
| `djast-db-migrations-specialist` | Safe migrations |
| `djast-celery-worker-engineer` | Async tasks, Beat |
| `djast-security-reviewer` | Auth, webhooks, secrets |
| `djast-docs-writer` | This handbook at `/docs/` |
| `djast-code-reviewer` | Pre-merge review |

Definitions: `.cursor/agents/djast-<role>.md` in the repo.

### Example workflows

**New feature**

1. `djast-architect` — plan apps, URLs, services  
2. `djast-backend-engineer` (+ `djast-db-migrations-specialist` for schema)  
3. `djast-frontend-engineer` — UI if needed  
4. `djast-qa-test-engineer` — tests  
5. `djast-docs-writer` — update `/docs/`  
6. `djast-code-reviewer` / `djast-security-reviewer` — before merge  

**Blog post**

1. `djast-seo-content-strategist` or `/new-blog-post`  
2. `djast-frontend-engineer` — template tweaks if needed  

**Deploy**

1. `djast-devops-deployer` + `/deploy-check`  
2. `djast-security-reviewer` — auth and payments in prod  

## Entry points in the repo

| File | Tool |
|------|------|
| `.cursorrules` | Cursor — index of rules, commands, agents |
| `CLAUDE.md` | Claude Code — same pointers |
| `.agentic/system_architecture.md` | Full stack reference for agents |
| `.agentic/coding_standards.md` | Coding conventions |

## App-specific agent docs

Some apps include deeper instructions for content APIs:

| App | File |
|-----|------|
| Blog | `src/blog/AGENT_INSTRUCTIONS.md` |
| Free tools | `src/free_tools/AGENT_INSTRUCTIONS.md` |

Use with `/new-blog-post`, `/new-free-tool`, or `djast-seo-content-strategist`.

## Tips

- **Small change in one file?** Rely on auto-attached rules; default chat is enough.  
- **Repeatable workflow?** Use a slash command.  
- **Multi-file feature or review?** Pick a `djast-*` agent.  
- **After user-visible changes**, run `/new-doc-page` or ask `djast-docs-writer` to update this handbook.
