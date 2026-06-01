# Tailwind Theme

djast uses **django-tailwind** with Tailwind CSS 3.4.

## Key Files

| File | Purpose |
|------|---------|
| `theme/static_src/tailwind.config.js` | Tailwind configuration |
| `theme/static_src/src/styles.css` | Source CSS with `@tailwind` directives |
| `theme/static/css/dist/styles.css` | Compiled output (auto-generated) |

## Development

`run.py` starts the Tailwind watcher automatically. To run it separately:

```bash
cd src
python manage.py tailwind start
```

This watches for changes and recompiles CSS.

## One-Off Build

```bash
cd src
python manage.py tailwind build
```

## Customizing

Edit `theme/static_src/tailwind.config.js` to:

- Add custom colors, fonts, spacing
- Extend the default theme
- Configure content paths for class scanning

```javascript
module.exports = {
  content: [
    '../templates/**/*.html',
    '../../**/templates/**/*.html',
  ],
  theme: {
    extend: {
      colors: {
        brand: '#6366f1',
      },
    },
  },
};
```

After editing config, restart the Tailwind watcher.

## Templates

Use Tailwind utility classes directly in Django templates:

```html
<div class="bg-gray-900 text-white p-4 rounded-lg">
  Hello world
</div>
```

Prefer utilities over custom CSS. Use `{% include %}` for reusable components.

## Production

CSS is compiled during `collectstatic`. Ensure Tailwind is built before
deploying:

```bash
cd src
python manage.py tailwind build
python manage.py collectstatic --noinput
```

## Troubleshooting

If styles don't load, see [Troubleshooting — Tailwind](/docs/troubleshooting/).
