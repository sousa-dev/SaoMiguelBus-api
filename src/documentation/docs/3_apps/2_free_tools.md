# Free Tools

SEO-rich free tool pages that act as lead magnets.

## URLs

| Path | Purpose |
|------|---------|
| `/tools/` | Searchable directory of all tools |
| `/tools/<slug>/` | Individual tool page with SEO + CTA |
| `/tools/category/<slug>/` | Category archive |
| `/tools/api/tools/` | REST API — list/create tools |
| `/tools/api/tools/<slug>/` | REST API — get/update/delete tool |
| `/tools/api/categories/` | REST API — categories |

## How Tools Work

Each tool has:

1. **Database record** — SEO metadata, CTA config, slug, category
2. **Django template** — interactive UI (pure HTML/JS, no server round-trip for most tools)

## Built-in Tools

| Tool | URL |
|------|-----|
| Django Secret Key Generator | `/tools/django-secret-key-generator/` |

## Adding a New Tool

See [Adding a Tool](/docs/customization/adding_a_tool) for the full workflow.

## Enable / Disable

```python
('free_tools', True),  # src/src/settings.py
```

## Agent Docs

See `free_tools/AGENT_INSTRUCTIONS.md` for programmatic tool creation via API.
