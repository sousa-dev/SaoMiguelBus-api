# Background Tasks

djast uses **Celery 5.4** with **Redis** for async task processing and
**django-celery-beat** for periodic scheduling.

## Architecture

```
Django App                    Celery Worker
    │                              │
    ├── task.delay() ──► Redis ──► executes task
    │                              │
    └── django-celery-beat ──► Redis ──► scheduled tasks
```

| Component | Role |
|-----------|------|
| **Redis** | Message broker + result backend |
| **Celery Worker** | Executes async tasks |
| **Celery Beat** | Schedules periodic tasks |
| **django-celery-beat** | Stores schedules in the database |

## Configuration

Set in `src/src/.env`:

```env
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

Celery settings are in `src/src/settings.py`. The Celery app loads on Django
startup via `src/src/__init__.py`.

## In This Section

| Page | Topic |
|------|-------|
| [Writing Tasks](/docs/background_tasks/writing_tasks) | Create `@shared_task` functions |
| [Calling Tasks](/docs/background_tasks/calling_tasks) | Dispatch from views/services |
| [Periodic Tasks](/docs/background_tasks/periodic_tasks) | Schedule via admin |
| [Running Locally](/docs/background_tasks/running_locally) | Start Redis, worker, beat |

## When You Need Celery

- Sending emails asynchronously
- Long-running data processing
- Scheduled cleanup or reporting jobs
- Any work that shouldn't block HTTP responses

For local dev without background tasks, you can skip Celery entirely — the web
app runs fine without it.
