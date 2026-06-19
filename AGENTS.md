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

`tenancy`, `transit`, `analytics`, `consent`, `billing`, `news`, `seismic`, `marketplace`, `trails`, `traffic`, `events`, `weather`, `compat`

**Reuse from boilerplate:** `stripe_payments`, `legal`, `user_management`, `documentation`, `shared`, `theme`

**Disable for SMB:** `app`, `free_tools`, `landing_page` (optional: keep `blog` for SEO)

### Viator tours (`events` app — shipped)

- `GET /api/v3/events/tours`, `GET /api/v3/events/tours/{product_code}` — Partner API proxy, Redis cache 1h; no ORM models.
- Requires `VIATOR_API_KEY` in `src/src/.env` (see `.env.example`: `VIATOR_PARTNER_ID`, `VIATOR_CAMPAIGN`, `VIATOR_DESTINATION_ID`).
- Bootstrap module key: `events` (`tenancy` migration `0010_enable_events_feature_flag`). SDD: `../SaoMiguelBus/SDD/04-api-design.md` §2.4, `09-modules.md` §7.

### Parish weather (`weather` app — shipped)

- `GET /api/v3/weather/parishes`, `GET /api/v3/weather/parishes/{slug}` — Open-Meteo proxy, Redis cache 1h per parish; `Parish` model seeded from `weather/data/parishes_sao_miguel.json`.
- No API key required (optional `OPEN_METEO_BASE_URL`, `OPEN_METEO_TIMEOUT` in `.env.example`).
- Celery beat: `weather.refresh_forecasts` hourly warms cache for all active parishes (one batched upstream call per island).
- Bootstrap module key: `weather` (`tenancy` migration `0011_enable_weather_feature_flag`).

### PDL Mini Bus (`minibus` app — shipped)

Urban Ponta Delgada network (lines A–D), separate from interurban `transit`. Read-only catalog + PDF/SVG documents sourced from [pdlminibus.pt](https://pdlminibus.pt).

- `GET /api/v3/minibus/lines`, `/lines/{slug}`, `/tariffs`, `/documents`, `/schematic`
- `GET /api/v3/minibus/documents/{slug}/file` — streams PDF/SVG (not raw `/media/` URLs)
- Seed: `minibus/data/catalog_sao_miguel.json`; binaries via `python manage.py import_minibus` (also runs on deploy in `runserver.sh`). Until media import completes, bundled files under `minibus/data/source/` are streamed as fallback.
- Bootstrap module key: `minibus` (`tenancy` migration `0013_enable_minibus_feature_flag`)
- Expo module linked from Buses (`transit`) promo card + profile info row

### Analytics reporting + stats dashboard (`analytics` app — shipped)

Read-side, **AUTH_KEY-protected** endpoints (via `X-Auth-Key` header or `?key=`) that aggregate stored analytics. v3 endpoints are tenant-scoped (`X-Island`); legacy ones are global.

| Endpoint | Purpose |
|---|---|
| `GET /api/v3/analytics/reports/overview` | v3 `AnalyticsEvent`: totals, time series, breakdowns (module, event_type, platform, locale) |
| `GET /api/v3/analytics/reports/events` | v3 raw events — paginated + filterable |
| `GET /api/v3/analytics/reports/properties` | v3 `properties` JSON: auto-discovered per-key top values + origin→destination routes (most-searched data). `?prop=` for one key |
| `GET /api/v3/analytics/reports/meta` | v3 distinct filter values + date bounds |
| `GET /api/v3/analytics/reports/legacy/overview` | legacy `Stat`: totals, series, breakdowns (request, top routes/origins/destinations, platform, language, day type, time of day) |
| `GET /api/v3/analytics/reports/legacy/events` | legacy raw stats — paginated |
| `GET /api/v3/analytics/reports/legacy/meta` | legacy distinct filter values |

- Params: `start`, `end` (`YYYY-MM-DD`), `interval` (`hour\|day\|month`, auto by range), `page`, `page_size`, plus per-source filters (`module`, `event_type`, `platform`, `locale` / `request`, `language`).
- Logic: `analytics/services_reporting.py`; views: `analytics/api_reporting.py`.
- `CORS_ALLOW_HEADERS` allows `x-auth-key` / `x-api-key` so the static dashboard can call cross-origin.
- **Dashboard:** `docs/` — zero-build umami-style HTML/CSS/JS for GitHub Pages (Settings → Pages → `/docs`). Tabs for Hub (v3) / Legacy, date-range presets, time-series chart, breakdowns, paginated table. Connection config (API base, AUTH key, island) lives in browser `localStorage`. See `docs/README.md`.

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

### Dokploy (single web container)

Use the repo-root **`Dockerfile`** — default **`CMD ["bash", "./runserver.sh"]`**. Do **not** override the start command unless you replicate the full sequence below.

On every deploy, `runserver.sh` runs (in order):

1. `collectstatic`
2. `migrate`
3. **`import_minibus --island ${DEFAULT_ISLAND_KEY:-sao-miguel}`** — copies bundled PDFs/SVG into `MEDIA_ROOT` (idempotent)
4. `bootstrap_feed_syncs`
5. `ensure_superuser`
6. Gunicorn

Required env (Dokploy **Environment** tab / repo-root `.env`):

```env
DEFAULT_ISLAND_KEY=sao-miguel
DEBUG=False
DB_HOST=...
DB_NAME=...
DB_USER=...
DB_PASSWORD=...
ALLOWED_HOSTS=staging.api.saomiguelhub.com,api.saomiguelbus.com
```

Optional but recommended: mount a persistent volume on **`/usr/src/app/media`** so imported minibus files survive redeploys. If media is empty, the API still streams from bundled `minibus/data/source/` as fallback.

Celery worker/beat containers use `celery-entrypoint.sh` (migrate only) — they do not need `import_minibus`.

### Agent tooling (boilerplate)

- `.cursor/commands/` — `/new-app`, `/new-api-endpoint`, `/new-task`, …
- `.cursor/agents/` — `djast-backend-engineer`, `djast-db-migrations-specialist`, …
- `boilerplate/CLAUDE.md` — entry point until promoted to root

### RevenueCat webhook (mobile IAP)

- Webhook: `POST /api/v3/billing/webhooks/revenuecat` — auth via `Authorization: <REVENUECAT_WEBHOOK_SECRET>` header.
- Client App User ID format: `smb_user_<django_user_pk>` (`billing.services.REVENUECAT_APP_USER_ID_PREFIX`). Anonymous `$RCAnonymousID:*` events are ignored (no backend entitlement until login transfer).
- Configure in RevenueCat dashboard: webhook URL + secret; enable **transfer purchases to new App User ID** on the client side so anonymous purchases move to `smb_user_<id>` on login.
- Required env: `REVENUECAT_WEBHOOK_SECRET` in `src/src/.env`.

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

## Agent docs API (LLM / Cursor)

Machine-readable context and OpenAPI for any agent:

| URL | Purpose |
|-----|---------|
| `GET /api/v3/agent-docs/` | Catalog of docs + OpenAPI links |
| `GET /api/v3/agent-docs/{slug}` | Single doc as JSON (`content` field) |
| `GET /api/v3/agent-docs/{slug}?raw=1` | Plain-text body only |
| `GET /api/schema/` | OpenAPI 3 schema (YAML; add `Accept: application/vnd.oai.openapi+json` for JSON) |
| `GET /api/docs/` | Swagger UI |
| `GET /api/docs/redoc/` | ReDoc |

**Slugs:** `agents-md`, `readme`, `env-example`, `ai-agents-handbook`, `feature-toggles`, `adding-an-app`, `traffic-readme`. The index also lists external SDD/webapp links.

---

## Cross-repo pointers

- **SDD:** `../SaoMiguelBus/SDD/` (or github.com/sousa-dev/SaoMiguelBus/tree/revamp/SDD)
- **Expo client:** `../SaoMiguelBus/`
- **Legacy webapp:** `../SaoMiguelBus-webapp/` (deprecated after cutover)
