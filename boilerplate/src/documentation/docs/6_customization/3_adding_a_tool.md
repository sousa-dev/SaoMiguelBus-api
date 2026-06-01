# Adding a Tool

Create a new free tool page at `/tools/<slug>/`.

## Overview

Each tool needs:

1. A **database record** (SEO metadata + CTA config)
2. A **Django template** (interactive UI)

## 1. Create the Database Record

Via Django admin (`/dashboard/admin/` → **Free tools**) or API:

| Field | Example |
|-------|---------|
| Title | JSON Formatter |
| Slug | `json-formatter` |
| Meta title | Free JSON Formatter — Online Tool |
| Meta description | Format and validate JSON instantly |
| Category | Developer Tools |
| CTA text / URL | Sign up for more tools |

Or via API at `/tools/api/tools/`.

## 2. Create the Template

```
free_tools/templates/free_tools/tools/json_formatter.html
```

The template implements the interactive UI. Most tools use pure HTML/JS with no
server round-trip.

## 3. Register the Template

Connect the tool slug to its template in the free_tools views (see
`free_tools/views.py` for the pattern used by existing tools).

## 4. Verify

Visit `/tools/json-formatter/` and confirm:

- [ ] Tool renders correctly
- [ ] SEO meta tags present (view page source)
- [ ] CTA displays
- [ ] Tool appears on `/tools/` index

## 5. Update Documentation

- Add to [Free Tools](/docs/apps/free_tools) built-in tools table
- Update [URL Map](/docs/architecture/url_map) if new routes added

See [Maintaining Docs](/docs/maintaining_docs/).

## Agent Reference

For programmatic creation, see `free_tools/AGENT_INSTRUCTIONS.md`.
