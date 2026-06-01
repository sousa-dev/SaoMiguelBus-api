# Database & Cache

## Database

| Environment | Engine | Location / Config |
|-------------|--------|-------------------|
| Development (`DEBUG=True`) | SQLite | `src/db.sqlite3` (automatic) |
| Production (`DEBUG=False`) | PostgreSQL | Env vars below |

### PostgreSQL Variables

```env
DB_NAME=postgres
DB_USER=your_user
DB_PASSWORD=your_password
DB_HOST=your_host
DB_PORT=5432
```

The switch happens automatically in `settings.py` based on `DEBUG`.

### Migrations

```bash
cd src
python manage.py makemigrations   # after model changes
python manage.py migrate          # apply migrations
```

## Cache

| Environment | Backend | Config |
|-------------|---------|--------|
| Development | In-memory (`LocMemCache`) | Default when `REDIS_URL` is empty |
| Production | Redis | Set `REDIS_URL` in `.env` |

```env
REDIS_URL=redis://localhost:6379/1
```

Redis database `1` is used for cache; database `0` is used for Celery.

## Docker Compose

PostgreSQL and Redis run as Compose services. Set connection values in
`src/src/.env` (see the Docker Compose section in `.env.example`), for example
`DB_HOST=db` and `CELERY_BROKER_URL=redis://redis:6379/0`.

See [Docker Compose](/docs/deployment/docker_compose).

## Resetting Local Database

```bash
cd src
rm db.sqlite3
python manage.py migrate
python manage.py createsuperuser
```

Only do this in development — never in production.
