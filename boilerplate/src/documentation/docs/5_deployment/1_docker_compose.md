# Docker Compose

The recommended way to deploy the full djast stack.

## Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| `db` | postgres:16-alpine | 5432 | PostgreSQL |
| `redis` | redis:7-alpine | 6379 | Celery broker + cache |
| `web` | Dockerfile | 8000 | Django + Gunicorn |
| `celery-worker` | Dockerfile | — | Task execution |
| `celery-beat` | Dockerfile | — | Periodic scheduler |

## Quick Start

```bash
# From repo root
cp src/src/.env.example src/src/.env
# Edit .env — uncomment the Docker Compose section for container hostnames (DB_HOST=db, etc.)

docker compose --env-file src/src/.env up -d --build
docker compose exec web python manage.py createsuperuser
```

Visit [http://localhost:8000](http://localhost:8000).

## Configuration

App settings are loaded via `env_file` (injected into the container process
environment). Compose accepts **either** file; missing files are ignored:

| File | Use case |
|------|----------|
| `.env` (repo root) | **Dokploy** — variables from the Environment tab are written here |
| `src/src/.env` | **Local** — copy from `.env.example` |

Nothing is hardcoded in `docker-compose.yml` except `${VAR:-default}` fallbacks for
ports and Postgres bootstrap (`DB_NAME` → `POSTGRES_DB`).

### Dokploy

1. Open your Compose app → **Environment** and set variables (same names as
   `src/src/.env.example`: `SECRET_KEY`, `DEBUG`, `DB_HOST`, `TEST_STRIPE_*`, etc.).
2. Dokploy writes them to `.env` next to `docker-compose.yml` on deploy — no
   `src/src/.env` in the repo is required.
3. Use Docker hostnames in Dokploy env:

| Variable | Value on Dokploy |
|----------|------------------|
| `DB_HOST` | `db` |
| `DB_PORT` | `5432` |
| `CELERY_BROKER_URL` | `redis://redis:6379/0` |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/0` |
| `REDIS_URL` | `redis://redis:6379/1` |
| `DEBUG` | `False` (prod) or `True` (staging → `TEST_*` Stripe keys) |
| `ALLOWED_HOSTS` | Your staging/production hostnames |
| `CORS_ALLOWED_ORIGINS` | `https://your-staging-domain` |
| `DB_USER` / `DB_PASSWORD` | Match Postgres; also bootstrap Django admin on first deploy |

### Local Docker

```bash
cp src/src/.env.example src/src/.env
# Uncomment the Docker Compose block (DB_HOST=db, redis URLs, …)
docker compose up -d --build
```

| `DEBUG` | Stripe keys | Django database |
|---------|-------------|-----------------|
| `False` | `STRIPE_*` | PostgreSQL (`db` service) |
| `True` | `TEST_*` | SQLite in `web` (Postgres still runs but Django ignores it) |

## Useful Commands

```bash
docker compose logs -f web              # Web server logs
docker compose logs -f celery-worker    # Worker logs
docker compose exec web python manage.py migrate
docker compose exec web python manage.py collectstatic --noinput
docker compose down                     # Stop all
docker compose down -v                  # Stop + wipe volumes
```

## Volumes

| Volume | Purpose |
|--------|---------|
| `postgres_data` | Database persistence |
| `redis_data` | Redis persistence |
| `static_files` | Collected static files |
| `media_files` | User uploads |

## Health Checks

Both `db` and `redis` services include health checks. `web`, `celery-worker`, and
`celery-beat` wait for healthy dependencies before starting.
