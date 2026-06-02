#!/usr/bin/env bash
# Run migrations then exec the Celery process (worker or beat).
# Ensures django_celery_beat tables exist before DatabaseScheduler starts.
set -euo pipefail

python manage.py migrate --no-input
exec "$@"
