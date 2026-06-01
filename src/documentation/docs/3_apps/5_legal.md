# Legal Pages

JSON-driven legal pages — privacy policy, terms of service, and licenses.

## URLs

| Path | Content |
|------|---------|
| `/legal/privacy-policy/` | Privacy policy |
| `/legal/terms-of-service/` | Terms of service |
| `/legal/licenses/` | Open-source licenses |

## Editing Content

Legal page content lives in JSON files:

```
src/legal/data/
├── privacy_policy.json
├── terms_of_service.json
└── licenses.json
```

Each JSON file contains structured sections that the template renders. Edit the
JSON directly — no code changes needed for content updates.

## Public Access

Legal paths (`/legal/`) are excluded from the site-wide login gate.

## Enable / Disable

```python
('legal', True),  # src/src/settings.py
```

## Adding a New Legal Page

1. Add a JSON file in `legal/data/`.
2. Add a view and URL pattern in `legal/views.py` and `legal/urls.py`.
3. Update [URL Map](/docs/architecture/url_map) and this page.
