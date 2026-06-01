# Vercel

Deploy djast to Vercel for serverless hosting.

## Configuration

Vercel config lives at `src/vercel.json`:

```json
{
  "builds": [{ "src": "src/wsgi.py", "use": "@vercel/python" }],
  "routes": [{ "src": "/(.*)", "dest": "src/wsgi.py" }]
}
```

## Limitations

| Feature | Vercel support |
|---------|----------------|
| Django web app | Yes |
| Celery worker | No |
| Celery beat | No |
| Redis | No (use external provider) |
| SQLite | No (use external PostgreSQL) |
| File uploads (media) | Limited — use external storage |

Vercel is best for **web-only** deployments without background tasks.

## Setup

1. Connect your GitHub repo to Vercel.
2. Set root directory to `src/`.
3. Add environment variables in Vercel dashboard:
   - `SECRET_KEY`
   - `DEBUG=False`
   - PostgreSQL vars (`DB_NAME`, `DB_USER`, etc.)
   - Stripe production keys
4. Deploy.

## Database

Use a managed PostgreSQL service (Neon, Supabase, Railway) and set connection
vars in Vercel env settings.

## Static Files

Run `collectstatic` as a build step or use Whitenoise (already in
requirements). Tailwind must be compiled before deploy.

## When to Use

- Demos and prototypes
- Marketing sites without background processing
- Low-traffic apps

For production SaaS with payments and background tasks, use
[Docker Compose](/docs/deployment/docker_compose).
