## Cursor Cloud specific instructions

This workspace contains three related Django repositories:

| Repository | Path | Port | Purpose |
|---|---|---|---|
| `djast` | `/agent/repos/djast` | 8000 | Main boilerplate product |
| `djast-landing-page` | `/agent/repos/djast-landing-page` | 8001 | Marketing site for djast.dev |
| `djast-starter` | `/agent/repos/djast-starter` | 8002 | Customer-downloadable starter template |

### Running services

Each repo follows the same pattern:

```
cd /agent/repos/<repo>
source .venv/bin/activate
cd src
python manage.py runserver 0.0.0.0:<port>
```

Tailwind watcher (required for CSS hot-reload during dev):
```
cd /agent/repos/<repo>
source .venv/bin/activate
cd src
python manage.py tailwind start
```

The repo's `run.py` script combines both (Tailwind + Django) but requires being run from the `src/` directory.

### Key gotchas

- **Database**: All repos use SQLite in development (`DEBUG=True`). No external DB needed.
- **`.env` location**: Environment files live at `<repo>/src/src/.env` (not the repo root). The `djast` and `djast-starter` repos provide `.env.example` with safe defaults. The `djast-landing-page` requires explicit values (no defaults) for `SECRET_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_SECRET`, `GITHUB_CLIENT_ID`, `GITHUB_SECRET`, and all Stripe keys — use placeholder values for dev.
- **Tailwind node_modules**: Located at `<repo>/src/theme/static_src/node_modules/`. Install via `python manage.py tailwind install` from the `src/` directory.
- **Static files**: Run `python manage.py collectstatic --noinput` before first serve or after Tailwind builds.
- **Tests**: `python manage.py test` from the `src/` directory. Tests use in-memory SQLite.
- **No Redis/PostgreSQL needed** for local development.
- **python3.12-venv** system package must be installed (`sudo apt-get install -y python3.12-venv`).
