# Customization

Where and how to customize djast for your product.

## Customization Map

| What | Where | Docs |
|------|-------|------|
| Feature toggles | `src/src/settings.py` `apps` list | [Feature Toggles](/docs/configuration/feature_toggles) |
| Secrets & env | `src/src/.env` | [Environment](/docs/get_started/environment) |
| UI / styling | `theme/static_src/tailwind.config.js` | [Tailwind Theme](/docs/customization/tailwind_theme) |
| Main app logic | `app/` | [Adding an App](/docs/customization/adding_an_app) |
| Payment flow | `stripe_payments/services.py` | [Stripe Payments](/docs/apps/stripe_payments) |
| Auth behavior | `user_management/middleware.py` | [User Management](/docs/apps/user_management) |
| Legal content | `legal/data/*.json` | [Legal](/docs/apps/legal) |
| Documentation | `documentation/docs/` | [Adding Docs](/docs/customization/adding_docs) |
| Blog content | Django admin | [Adding a Blog Post](/docs/customization/adding_a_blog_post) |
| Free tools | DB + templates | [Adding a Tool](/docs/customization/adding_a_tool) |
| AI-assisted workflows | `.cursor/commands/`, `.cursor/agents/` | [AI Agents](/docs/get_started/ai_agents) |

## In This Section

| Page | Topic |
|------|-------|
| [Tailwind Theme](/docs/customization/tailwind_theme) | CSS compilation and config |
| [Adding an App](/docs/customization/adding_an_app) | New Django app workflow |
| [Adding a Tool](/docs/customization/adding_a_tool) | New free tool page |
| [Adding a Blog Post](/docs/customization/adding_a_blog_post) | Content via admin |
| [Adding Docs](/docs/customization/adding_docs) | New `/docs` page |
| [Event Tracking](/docs/customization/event_tracking) | GA4 events, `data-ga-*`, tool/blog patterns |

## Architecture Conventions

When customizing code, follow djast conventions:

- Business logic in `services.py`, not views
- Type hints on all functions
- Google-style docstrings on public APIs

See [Architecture](/docs/architecture/) for details.

## Keeping Docs in Sync

Any customization that changes user-visible behavior must update `/docs`.
See [Maintaining Docs](/docs/maintaining_docs/).
