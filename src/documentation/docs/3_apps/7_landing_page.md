# Landing Page

Optional marketing landing page that replaces the dashboard at `/`.

## URLs

| Config | `/` shows | Dashboard at |
|--------|-----------|--------------|
| `landing_page=False` | Dashboard | `/` |
| `landing_page=True` | Landing page | `/app/` |

## Enable

```python
# src/src/settings.py
('landing_page', True),
('app', True),  # required — landing page links to /app/
```

Restart the dev server.

## Customization

Templates live in `landing_page/templates/landing_page/`. Edit HTML and Tailwind
classes directly.

Static assets: `landing_page/static/landing_page/`.

## Disable

```python
('landing_page', False),
```

Dashboard returns to `/`.
