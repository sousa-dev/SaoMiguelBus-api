# São Miguel Bus API (revamp)

Django REST API for São Miguel Island bus schedules and the **Azores Hub** platform. On branch **`revamp`**: legacy production code is frozen under [`legacy/`](./legacy/); the new backend is built from the **djast** starter in [`boilerplate/`](./boilerplate/) and promoted to this repo root.

Planning docs: [SaoMiguelBus/SDD](https://github.com/sousa-dev/SaoMiguelBus/tree/revamp/SDD).

## Layout

| Path | Purpose |
|------|---------|
| [`legacy/`](./legacy/) | Django 3.0 API — last shipped version, compat contract, ETL source (`legacy/src/db.sqlite3`, `data.json`, `scripts/csv/`) |
| [`boilerplate/`](./boilerplate/) | Vendored [djast](https://djast.dev) starter — upstream reference |
| **Root `src/`** | New Django 5 modular monolith (promoted from boilerplate) |

## New backend structure (post-promotion)

```
SaoMiguelBus-api/
├── src/                    # run all commands from here
│   ├── manage.py
│   ├── run.py              # dev: Django + Tailwind
│   ├── src/                # settings, urls, celery, .env
│   ├── tenancy/            # Island, tenant middleware
│   ├── transit/            # schedules, directions proxy
│   ├── compat/             # legacy /api/v1 + /api/v2 shim
│   ├── analytics/ consent/ billing/ news/ …
│   ├── stripe_payments/    # from boilerplate
│   └── user_management/ legal/ documentation/ …
├── docker-compose.yml
└── setup.py
```

Feature toggles: `src/src/settings.py` → `apps = [...]` list.

## Quick start (new backend — after boilerplate promotion)

```bash
python setup.py
cp src/src/.env.example src/src/.env   # set SECRET_KEY, ports, etc.
cd src
python run.py                          # http://${WEB_HOST}:${WEB_PORT} (default 127.0.0.1:8000)
```

Tests: `cd src && python manage.py test`

Celery (optional): Redis + `celery -A src worker` + beat — see `boilerplate/README.md`.

## Legacy API (still runnable)

```bash
cd legacy/src
python3 manage.py runserver 0.0.0.0:${WEB_PORT:-8000}
```

Dev uses SQLite at `legacy/src/db.sqlite3` (pre-seeded). Production uses Postgres via `DATABASE_URL`.

## Import legacy data into new DB

One-shot orchestrator (idempotent; see SDD [`05-data-migration`](https://github.com/sousa-dev/SaoMiguelBus/blob/revamp/SDD/05-data-migration.md)):

```bash
cd src
python manage.py migrate                    # new schema first
python manage.py import_legacy \
  --legacy-db sqlite:///$(pwd)/../legacy/src/db.sqlite3 \
  --island sao-miguel

# Or production legacy Postgres:
# python manage.py import_legacy --legacy-db "$LEGACY_DATABASE_URL"

# Single step / dry-run:
python manage.py migrate_legacy stops
python manage.py import_legacy --dry-run
python manage.py validate_legacy_parity --sample-size 100
```

Commands live under `tenancy/management/commands/` (implementation Phase 1).

## Related repos

| Repo | Role |
|------|------|
| [SaoMiguelBus](https://github.com/sousa-dev/SaoMiguelBus) | Expo app + **SDD/** |
| [SaoMiguelBus-webapp](https://github.com/sousa-dev/SaoMiguelBus-webapp) | Legacy PWA — deprecated after cutover |

## Agent docs

- Root: [`AGENTS.md`](./AGENTS.md)
- Boilerplate (upstream): [`boilerplate/AGENTS.md`](./boilerplate/AGENTS.md), [`boilerplate/CLAUDE.md`](./boilerplate/CLAUDE.md)
