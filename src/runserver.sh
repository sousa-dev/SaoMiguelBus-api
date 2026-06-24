#!/usr/bin/env bash
set -euo pipefail

ISLAND_KEY="${DEFAULT_ISLAND_KEY:-sao-miguel}"

echo "[deploy] collectstatic"
python manage.py collectstatic --no-input

echo "[deploy] migrate"
python manage.py migrate --no-input

echo "[deploy] import_minibus (island=${ISLAND_KEY})"
python manage.py import_minibus --island "${ISLAND_KEY}"

echo "[deploy] bootstrap_feed_syncs"
python manage.py bootstrap_feed_syncs

echo "[deploy] bootstrap_minibus_route_shapes (island=${ISLAND_KEY})"
python manage.py bootstrap_minibus_route_shapes --island "${ISLAND_KEY}"

echo "[deploy] ensure_superuser"
python manage.py ensure_superuser

echo "[deploy] gunicorn"
gunicorn src.wsgi --bind="0.0.0.0:${WEB_CONTAINER_PORT:-8000}" --workers="${GUNICORN_WORKERS:-3}" --timeout 120
