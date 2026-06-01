# Periodic Tasks

Schedule recurring tasks with **django-celery-beat**.

## Via Django Admin

1. Start Celery worker and beat (see [Running Locally](/docs/background_tasks/running_locally)).
2. Go to `/dashboard/admin/` → **Periodic Tasks**.
3. Create a new periodic task:
   - **Name**: descriptive label
   - **Task**: dotted path, e.g. `app.tasks.cleanup_expired_sessions`
   - **Interval** or **Crontab**: schedule
   - **Enabled**: checked

Beat reads schedules from the database and dispatches to the worker.

## Crontab Examples

| Schedule | Crontab |
|----------|---------|
| Every day at midnight | `0 0 * * *` |
| Every hour | `0 * * * *` |
| Every Monday 9am | `0 9 * * 1` |

## Programmatic Setup

Create `PeriodicTask` and `CrontabSchedule`/`IntervalSchedule` objects via
Django ORM or a data migration for reproducible schedules.

## Requirements

Both must be running:

```bash
celery -A src worker --loglevel=info
celery -A src beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

In Docker Compose, `celery-beat` and `celery-worker` services handle this
automatically.

## Adding a New Periodic Task

When you add a scheduled task:

1. Implement the `@shared_task` in `<app>/tasks.py`.
2. Register the schedule in admin (or via migration).
3. Update this page or [Writing Tasks](/docs/background_tasks/writing_tasks).
