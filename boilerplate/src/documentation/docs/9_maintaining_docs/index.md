# Maintaining Documentation

This page is the contract between human developers and AI agents for keeping
`/docs` accurate.

## Why This Matters

`src/documentation/docs/` is the **user-facing handbook** served at `/docs/`.
It is part of the product — not optional notes. When code changes user-visible
behavior, the docs must change too.

## The Rule

> Any code change that alters user-visible behavior **must** be accompanied by
> an edit to the matching `.md` file under `src/documentation/docs/`.

A PR or commit that changes covered code without updating `/docs` is **incomplete**.

This rule is enforced in:

- `.agentic/coding_standards.md` §11 (canonical)
- `.cursorrules` → Documentation Maintenance
- `CLAUDE.md` → Documentation Maintenance

## Change → Doc Mapping

| Code change | Update these docs |
|-------------|-------------------|
| New env var in `settings.py` | `1_get_started/3_environment.md` + relevant `2_configuration/` page + `5_deployment/4_production_env.md` + `src/src/.env.example` |
| New app in `apps` list | `2_configuration/1_feature_toggles.md` + `3_apps/index.md` + new `3_apps/N_<app>.md` |
| New URL pattern | `7_architecture/1_url_map.md` + relevant app page in `3_apps/` |
| Auth / OAuth change | `2_configuration/2_auth_oauth.md` + `3_apps/6_user_management.md` |
| Stripe change | `2_configuration/3_stripe.md` + `3_apps/3_stripe_payments.md` |
| Email backend change | `2_configuration/4_email.md` |
| Database / cache change | `2_configuration/5_database_cache.md` |
| New Celery task pattern | `4_background_tasks/` (relevant page) |
| Deployment change | `5_deployment/` (relevant page) |
| New customization workflow | `6_customization/` (relevant page) |
| Architecture change | `7_architecture/` + `.agentic/system_architecture.md` |
| Setup step change | `1_get_started/` (install, first_run, or environment) |
| New troubleshooting scenario | `8_troubleshooting/index.md` |
| Docs engine change | `3_apps/4_documentation.md` + `6_customization/5_adding_docs.md` |

When unsure, add a note to the closest existing page rather than skipping.

## File Naming Convention

```
src/documentation/docs/
├── N_section_name/          # e.g. 2_configuration/
│   ├── index.md             # section landing → /docs/section_name/
│   ├── 1_page_name.md       # → /docs/section_name/page_name
│   └── 2_another.md         # → /docs/section_name/another
```

- `N` controls sidebar sort order.
- Numeric prefix is stripped for URLs and display names.
- The engine auto-discovers new files — no code changes needed.

## How to Preview

```bash
cd src
python run.py
```

Visit [http://127.0.0.1:8000/docs/](http://127.0.0.1:8000/docs/).

Search: [http://127.0.0.1:8000/docs/search/](http://127.0.0.1:8000/docs/search/)

## Agent Checklist (Before Declaring Done)

1. Identify which user-visible behavior changed.
2. Look up the change in the mapping table above.
3. Edit or create the matching `.md` file(s).
4. Add internal links from section index pages if adding new pages.
5. Verify the page renders at `/docs/` without 404.

## Human Checklist

Same as above. When reviewing PRs, reject changes that touch covered code
without doc updates.

## Relationship to Agent Docs

| Audience | Location | Purpose |
|----------|----------|---------|
| Humans | `src/documentation/docs/` → `/docs/` | How to use and customize djast |
| Humans (AI tools) | `/docs/get_started/ai_agents` | Slash commands, rules, `djast-*` agents |
| AI agents | `.agentic/`, `.cursor/`, `.cursorrules`, `CLAUDE.md` | How to write code in djast |
| App-specific agents | `<app>/AGENT_INSTRUCTIONS.md` | API references for blog, tools |

When architecture changes, update **both** `.agentic/system_architecture.md` and
the relevant `/docs` pages.

## Adding This Section

Detailed instructions for adding new doc pages:
[Adding Docs](/docs/customization/adding_docs).
