#!/usr/bin/env bash
set -euo pipefail

ISLAND_KEY="${DEFAULT_ISLAND_KEY:-sao-miguel}"

echo "[deploy] collectstatic"
python manage.py collectstatic --no-input

echo "[deploy] migrate"
python manage.py migrate --no-input

echo "[deploy] bootstrap_atlas"
python manage.py bootstrap_atlas

echo "[deploy] import_minibus (island=${ISLAND_KEY})"
python manage.py import_minibus --island "${ISLAND_KEY}"

echo "[deploy] bootstrap_feed_syncs"
python manage.py bootstrap_feed_syncs

# Reconcile AtlasTrail from whatever trails.Trail currently holds. DB-only and fast (no
# network), so it is safe in the startup path. bootstrap_feed_syncs above only *queues* the
# trails sync onto Celery, so on a first deploy this step runs against the pre-sync data —
# that is fine and deliberate: trails.services.sync_all_open_data() propagates to atlas itself
# when the queued sync finishes, and this line guarantees a redeploy still reconciles atlas
# even when the Celery broker is unreachable.
#
# Non-fatal on purpose: this script runs under `set -e`, and an atlas reconcile is never worth
# black-holing a deploy before gunicorn binds. Same stance bootstrap_atlas documents.
echo "[deploy] import_atlas (trails, all islands)"
python manage.py import_atlas --source trails --all-islands \
  || echo "[deploy] import_atlas failed — continuing (atlas will catch up on the next trails sync)"

echo "[deploy] bootstrap_minibus_route_shapes (island=${ISLAND_KEY})"
python manage.py bootstrap_minibus_route_shapes --island "${ISLAND_KEY}"

echo "[deploy] bootstrap_azoresbus"
python manage.py bootstrap_azoresbus

echo "[deploy] ensure_superuser"
python manage.py ensure_superuser

echo "[deploy] gunicorn"
gunicorn src.wsgi --bind="0.0.0.0:${WEB_CONTAINER_PORT:-8000}" --workers="${GUNICORN_WORKERS:-3}" --timeout 120
