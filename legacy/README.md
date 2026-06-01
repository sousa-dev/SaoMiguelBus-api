# Legacy São Miguel Bus API

This directory holds the **pre-revamp** Django 3.0 / DRF backend, deployment config, scripts, and integration docs from the last production version.

| Path | Contents |
|------|----------|
| `src/` | Django project (`manage.py`, `app/`, `db.sqlite3`, requirements) |
| `config/` | nginx and deployment config |
| `scripts/` | Data import / ETL utilities |
| `plan/` | Stripe and subscription implementation plans |
| `docker-compose.yml`, `DockerFile`, `captain-definition` | Container / CapRover deploy |
| `FRONTEND_INTEGRATION_GUIDE.md`, `SUBSCRIPTION_*.md` | Client integration notes |

**Active revamp work** will be added at the repository root (e.g. `djast` backend layout per the mobile repo [`SDD/`](https://github.com/sousa-dev/SaoMiguelBus/tree/revamp/SDD)).

## Running the legacy API locally

```bash
cd legacy/src
pip install -r requirements.txt
# Python 3.12+: pip install 'psycopg2-binary>=2.9'
python3 manage.py runserver 0.0.0.0:8000
```

Tests: `python3 manage.py test` from `legacy/src`.
