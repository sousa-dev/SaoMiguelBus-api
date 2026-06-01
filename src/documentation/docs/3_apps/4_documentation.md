# Documentation Engine

The markdown documentation engine you're reading right now.

## URLs

| Path | Purpose |
|------|---------|
| `/docs/` | Documentation home |
| `/docs/<section>/` | Section index |
| `/docs/<section>/<page>/` | Individual page |
| `/docs/search/?q=...` | Full-text search |

## Content Location

All docs live in:

```
src/documentation/docs/
├── 1_get_started/
│   ├── index.md
│   ├── 1_install.md
│   └── ...
├── 2_configuration/
└── ...
```

## File Naming Convention

| Pattern | Example | URL |
|---------|---------|-----|
| Section dir | `1_get_started/` | `/docs/get_started/` |
| Page file | `1_install.md` | `/docs/get_started/install` |
| Section index | `index.md` | `/docs/get_started/` |

Numeric prefixes (`1_`, `2_`, …) control sidebar order. The engine strips them
for URLs and display names.

## Adding Pages

See [Adding Docs](/docs/customization/adding_docs) for step-by-step instructions.

## Markdown Features

Supported via `markdown2` extras:

- Fenced code blocks
- Tables
- Raw HTML (e.g. platform tabs on the Install page)

## Enable / Disable

```python
('documentation', True),  # src/src/settings.py
```

## Maintaining Docs

When you or an AI agent changes code that affects user-visible behavior, update
the matching page. See [Maintaining Docs](/docs/maintaining_docs/).
