# AGENTS.md

## Overview

São Miguel Bus API — branch **`revamp`**.

| Area | Path | Status |
|------|------|--------|
| **Legacy API** | `legacy/src/` | Django 3.0 — frozen, ETL + compat reference |
| **New backend** | `src/` (promoted from `boilerplate/`) | Django 5 via **djast** — Azores Hub per [SDD](https://github.com/sousa-dev/SaoMiguelBus/tree/revamp/SDD) |
| **Planning** | `SaoMiguelBus/SDD/` (sibling repo) | Source of truth for architecture |

---

## New backend (djast / boilerplate)

After promoting `boilerplate/` to root, all commands run from **`src/`**.

### Setup & run

```bash
cd SaoMiguelBus-api
python setup.py
cp src/src/.env.example src/src/.env
cd src
python run.py                    # Django + Tailwind — http://${WEB_HOST}:${WEB_PORT} (default 127.0.0.1:8000)
```

Set ports in `src/src/.env`:

```
WEB_HOST=127.0.0.1
WEB_PORT=8000
DB_PORT=5432
REDIS_HOST=localhost
REDIS_PORT=6379
```

Docker Compose host mappings: `WEB_PORT`, `WEB_CONTAINER_PORT`, `DB_PORT_EXPOSE`, `REDIS_PORT_EXPOSE`.

### Conventions (follow boilerplate)

| Pattern | Location |
|---------|----------|
| Feature toggles | `src/src/settings.py` → `apps = [(name, bool), ...]` |
| Business logic | `<app>/services.py` |
| REST API | `<app>/api.py` + `serializers.py` + `urls.py` |
| Celery tasks | `<app>/tasks.py` — `@shared_task` |
| Secrets | `src/src/.env` |
| Add an app | Toggle + `startapp` — see `boilerplate/src/documentation/docs/6_customization/2_adding_an_app.md` |

### SMB domain apps (to add via toggles)

`tenancy`, `transit`, `analytics`, `consent`, `billing`, `news`, `seismic`, `marketplace`, `trails`, `traffic`, `events`, `compat`

**Reuse from boilerplate:** `stripe_payments`, `legal`, `user_management`, `documentation`, `shared`, `theme`

**Disable for SMB:** `app`, `free_tools`, `landing_page` (optional: keep `blog` for SEO)

### Viator tours (`events` app — shipped)

- `GET /api/v3/events/tours`, `GET /api/v3/events/tours/{product_code}` — Partner API proxy, Redis cache 1h; no ORM models.
- Requires `VIATOR_API_KEY` in `src/src/.env` (see `.env.example`: `VIATOR_PARTNER_ID`, `VIATOR_CAMPAIGN`, `VIATOR_DESTINATION_ID`).
- Bootstrap module key: `events` (`tenancy` migration `0010_enable_events_feature_flag`). SDD: `../SaoMiguelBus/SDD/04-api-design.md` §2.4, `09-modules.md` §7.

### Legacy data import

```bash
cd src
python manage.py migrate
python manage.py import_legacy --legacy-db sqlite:///../legacy/src/db.sqlite3 --island sao-miguel
python manage.py migrate_legacy stops          # single step, re-runnable
python manage.py validate_legacy_parity
```

### Webapp drop-in deploy (compat API)

The new backend exposes the **same URLs** the legacy webapp calls. Point `api.saomiguelbus.com` here after import:

| Webapp calls | Compat handler |
|---|---|
| `GET /api/v2/stops` | ✓ |
| `GET /api/v2/webapp/load` | ✓ |
| `GET /api/v2/route` | ✓ |
| `POST /api/v2/like\|dislike/<id>` | ✓ |
| `GET /api/v1/gmaps` | ✓ (needs `GOOGLE_MAPS_API_KEY`) |
| `POST /api/v1/stat` | ✓ |
| `GET /api/v1/ad`, `POST /api/v1/ad/click` | ✓ |
| `POST /api/v1/subscription/verify/` | ✓ |

Required env (`src/src/.env`):

```
AUTH_KEY=SMBFj56xBCLc986j6odk3AK6fJa95k   # hardcoded in webapp JS
GOOGLE_MAPS_API_KEY=<prod key>
DEFAULT_ISLAND_KEY=sao-miguel
CORS_ALLOW_ALL_ORIGINS=True
ALLOWED_HOSTS=api.saomiguelbus.com,127.0.0.1,localhost
```

Production import from legacy Postgres:

```bash
python manage.py import_legacy --legacy-db "$LEGACY_DATABASE_URL"
```

Or from a JSON export (deploy `main-temp`, download, then import):

```bash
# 1. Start export (returns immediately with job_id)
curl 'https://api.saomiguelbus.com/api/v1/export/legacy?key=$AUTH_KEY'

# 2. Poll until status is "completed"
curl 'https://api.saomiguelbus.com/api/v1/export/legacy/status?key=$AUTH_KEY&job_id=JOB_ID'

# 3. Download file
curl -o /tmp/smb_legacy_export.json \
  'https://api.saomiguelbus.com/api/v1/export/legacy/download?key=$AUTH_KEY&job_id=JOB_ID'

python manage.py import_legacy --export-file /tmp/smb_legacy_export.json

# Large export (400MB+): split into batches, then queue on Celery (low memory)
python3 scripts/split_legacy_export.py \
  --input final_smb_legacy_export.json \
  --output-dir smb_export_batches \
  --batch-size 5000
# Or memory-safe from pull checkpoint:
# python3 scripts/split_legacy_export.py --checkpoint-dir final.json.checkpoint --output-dir smb_export_batches

python manage.py import_legacy \
  --export-dir media/legacy_imports/smb_export_batches \
  --essential-only \
  --async

# Monitor: Django admin → Legacy import jobs (current_step, step_reports, errors)
# Cancel stale/failing Celery work:
curl -X POST 'https://api.saomiguelbus.com/api/v1/ops/celery/cancel-all?key=$AUTH_KEY'
# Or: python manage.py cancel_celery_jobs
```

Importer reads: `legacy/src/db.sqlite3`, `legacy/src/data.json`, `legacy/scripts/csv/`, `legacy/scripts/groups.json`, or `--legacy-db` Postgres URL. Never writes to legacy DB.

### Tests

```bash
cd src && python manage.py test
```

### Docker (full stack)

```bash
cp src/src/.env.example src/src/.env
docker compose up -d --build
```

Services: `db`, `redis`, `web`, `celery-worker`, `celery-beat`.

### Agent tooling (boilerplate)

- `.cursor/commands/` — `/new-app`, `/new-api-endpoint`, `/new-task`, …
- `.cursor/agents/` — `djast-backend-engineer`, `djast-db-migrations-specialist`, …
- `boilerplate/CLAUDE.md` — entry point until promoted to root

---

## Legacy API

### Run

```bash
cd legacy/src
python3 manage.py runserver 0.0.0.0:${WEB_PORT:-8000}
```

Dev: SQLite at `legacy/src/db.sqlite3` (pre-seeded). Prod: `DATABASE_URL` → Postgres.

### Tests

```bash
cd legacy/src
python3 manage.py test
```

### Legacy caveats

- `psycopg2-binary==2.8.6` incompatible with Python 3.12+ — use `psycopg2-binary>=2.9` after `pip install -r requirements.txt`.
- `DATABASE_URL` unset → SQLite in dev.
- `GOOGLE_MAPS_API_KEY` / `AUTH_KEY` default to dummy values — directions need real keys.
- `ALLOWED_HOSTS` includes `127.0.0.1`.
- `Subscription` model is in **`subscriptions`** app (`db_table='subscriptions'`), not `app`.

### Legacy URL surface (compat must cover)

See SDD `04-api-design.md` §4 — full inventory from `legacy/src/SaoMiguelBus/urls.py`.

---

## Cross-repo pointers

- **SDD:** `../SaoMiguelBus/SDD/` (or github.com/sousa-dev/SaoMiguelBus/tree/revamp/SDD)
- **Expo client:** `../SaoMiguelBus/`
- **Legacy webapp:** `../SaoMiguelBus-webapp/` (deprecated after cutover)
