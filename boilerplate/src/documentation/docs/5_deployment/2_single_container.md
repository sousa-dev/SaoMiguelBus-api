# Single Container

Deploy djast as a standalone Docker image without Compose.

## Build

```bash
# From repo root
docker build -t djast .
```

## Run

```bash
docker run -p 8000:8000 --env-file src/src/.env djast
```

## What the Container Does

The Dockerfile runs `runserver.sh` which:

1. Collects static files
2. Runs migrations
3. Starts Gunicorn on port 8000

## External Dependencies

A single container does **not** include PostgreSQL, Redis, or Celery. You must
provide:

| Service | Required for |
|---------|--------------|
| PostgreSQL | Production database (`DEBUG=False`) |
| Redis | Celery tasks + cache (optional) |

Point env vars to external services:

```env
DEBUG=False
DB_HOST=your-postgres-host
DB_NAME=postgres
DB_USER=your_user
DB_PASSWORD=your_password
CELERY_BROKER_URL=redis://your-redis-host:6379/0
REDIS_URL=redis://your-redis-host:6379/1
```

## Celery

Run worker and beat as separate containers or processes pointing to the same
Redis broker. See [Docker Compose](/docs/deployment/docker_compose) for the
full multi-service setup.

## When to Use

- Simple deployments with managed PostgreSQL (RDS, Supabase, etc.)
- Platforms that run one container per app
- When you don't need Celery

For the full stack with zero external setup, prefer Docker Compose.
