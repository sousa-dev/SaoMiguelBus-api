# AGENTS.md

## Cursor Cloud specific instructions

### Overview

São Miguel Bus API — on the `revamp` branch, **legacy** Django 3.0 code is under `legacy/src/`. New backend work will be added at the repo root. Uses SQLite in dev, PostgreSQL in production (controlled by `ENVIRONMENT` env var).

### Running the legacy API

```bash
cd /agent/repos/SaoMiguelBus-api/legacy/src
python3 manage.py runserver 0.0.0.0:8000
```

Dev mode uses SQLite (no external DB needed). The database file at `legacy/src/db.sqlite3` contains pre-seeded route/stop data.

### Running tests

```bash
cd /agent/repos/SaoMiguelBus-api/legacy/src
python3 manage.py test
```

### Non-obvious caveats

- `psycopg2-binary==2.8.6` in `legacy/src/requirements.txt` is incompatible with Python 3.12+. Install `psycopg2-binary>=2.9` after running `pip install -r requirements.txt` to fix the import error. This only affects the build from source; the newer binary wheel works fine.
- The settings file imports `dj_database_url` and calls `.config()` which reads `DATABASE_URL` env var. In dev (no `DATABASE_URL` set), this is a no-op and SQLite is used.
- `GOOGLE_MAPS_API_KEY` and `AUTH_KEY` default to dummy values in dev — the step-by-step directions feature won't work without a real key, but all other endpoints function normally.
- `ALLOWED_HOSTS` includes `127.0.0.1` so local dev server works out of the box.
