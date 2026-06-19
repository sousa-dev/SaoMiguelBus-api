#!/usr/bin/env bash
set -euo pipefail

python manage.py collectstatic --no-input
python manage.py migrate --no-input
python manage.py import_minibus
python manage.py bootstrap_feed_syncs
python manage.py ensure_superuser
gunicorn src.wsgi --bind="0.0.0.0:${WEB_CONTAINER_PORT:-8000}" --workers="${GUNICORN_WORKERS:-3}" --timeout 120
