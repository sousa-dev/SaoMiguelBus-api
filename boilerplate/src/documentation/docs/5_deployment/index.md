# Deployment

djast supports multiple deployment targets.

## Options Matrix

| Target | Best for | Celery/Redis | Database |
|--------|----------|--------------|----------|
| [Docker Compose](/docs/deployment/docker_compose) | Full production stack | Yes | PostgreSQL |
| [Single Container](/docs/deployment/single_container) | Simple Docker deploy | Manual | External DB |
| [Vercel](/docs/deployment/vercel) | Serverless / demo | No | External DB |
| Local dev | Development | Optional | SQLite |

## Pre-Deployment Checklist

- [ ] Set `DEBUG=False` in production `.env`
- [ ] Set a strong `SECRET_KEY`
- [ ] Configure PostgreSQL env vars
- [ ] Set production Stripe keys (no `TEST_` prefix)
- [ ] Set `RESEND_API_KEY` and `DEFAULT_FROM_EMAIL`
- [ ] Configure `ALLOWED_HOSTS` in `settings.py`
- [ ] Run `collectstatic`
- [ ] Set up Stripe webhook for production domain

See [Production Environment](/docs/deployment/production_env) for the full
variable list.

## Static Files

Tailwind CSS is compiled to `theme/static/`. In production:

```bash
cd src
python manage.py collectstatic --noinput
```

WhiteNoise middleware + `collectstatic` serve `/static/` in production (Gunicorn/Docker).

## In This Section

| Page | Topic |
|------|-------|
| [Docker Compose](/docs/deployment/docker_compose) | Recommended full-stack deploy |
| [Single Container](/docs/deployment/single_container) | Standalone Docker image |
| [Vercel](/docs/deployment/vercel) | Serverless deployment |
| [Production Environment](/docs/deployment/production_env) | Required env vars |
