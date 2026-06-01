# Built-in Apps

djast ships with pre-built apps you enable or disable via the `apps` list in
`src/src/settings.py`.

## App Overview

| App | URL Prefix | Docs |
|-----|------------|------|
| **app** | `/` or `/app/` | Main dashboard |
| **landing_page** | `/` (when enabled) | [Landing Page](/docs/apps/landing_page) |
| **user_management** | `/login/`, `/logout/` | [User Management](/docs/apps/user_management) |
| **documentation** | `/docs/` | [Documentation](/docs/apps/documentation) |
| **blog** | `/blog/` | [Blog](/docs/apps/blog) |
| **free_tools** | `/tools/` | [Free Tools](/docs/apps/free_tools) |
| **stripe_payments** | `/payment/` | [Stripe Payments](/docs/apps/stripe_payments) |
| **legal** | `/legal/` | [Legal](/docs/apps/legal) |

## Toggle an App

```python
# src/src/settings.py
('blog', False),  # disables /blog/ entirely
```

Restart the dev server after changes.

## Adding Your Own App

See [Adding an App](/docs/customization/adding_an_app) for the full workflow.

## Agent Instructions

Some apps include agent-specific docs in the codebase:

| App | Agent doc |
|-----|-----------|
| blog | `blog/AGENT_INSTRUCTIONS.md` |
| free_tools | `free_tools/AGENT_INSTRUCTIONS.md` |

These are for AI agents working in the codebase. Human docs live here at `/docs/`.

For slash commands (`/new-blog-post`), path rules, and `djast-*` custom agents, see
[AI Agents, Rules & Commands](/docs/get_started/ai_agents).
