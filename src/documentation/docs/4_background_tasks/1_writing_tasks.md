# Writing Tasks

Create a `tasks.py` in any Django app.

## Basic Pattern

```python
# app/tasks.py
from __future__ import annotations

import logging

from celery import shared_task
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_welcome_email(self, *, user_id: int) -> dict[str, str | int]:
    """Send a welcome email to a newly registered user.

    Args:
        user_id: Primary key of the User to email.

    Returns:
        Status dict with user_id and result.
    """
    try:
        user = User.objects.get(id=user_id)
        # send email logic here
        logger.info("Welcome email sent to user %s", user_id)
        return {"status": "sent", "user_id": user_id}
    except User.DoesNotExist:
        logger.error("User %s not found", user_id)
        raise
    except Exception as exc:
        logger.exception("Failed to send welcome email")
        raise self.retry(exc=exc) from exc
```

## Rules

| Rule | Why |
|------|-----|
| Use `@shared_task` | Never import the Celery app directly |
| Accept JSON-serializable args | Pass IDs, not ORM objects |
| Use keyword-only args after `*` | Clear task signatures |
| Set `max_retries` and `default_retry_delay` | Graceful failure handling |
| Use `bind=True` for `self.retry()` | Retry on transient errors |
| Design for idempotency | Safe to run the same task twice |
| Log extensively | Background failures are hard to debug |
| Wrap DB mutations in `transaction.atomic()` | Data integrity |

## Time Limits

Global limits in `settings.py`:

- Hard limit: 30 minutes
- Soft limit: 25 minutes

Override per task with `time_limit` and `soft_time_limit` kwargs on
`@shared_task`.

## Example Task Location

See `app/tasks.py` for the reference implementation shipped with djast.
