"""Background tasks for the app module.

Define Celery tasks here using the ``@shared_task`` decorator.
Tasks should be idempotent (safe to retry) and accept only
JSON-serializable arguments.

Example usage from views or services::

    from app.tasks import example_task
    example_task.delay(user_id=42)
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def example_task(self, *, user_id: int | None = None) -> dict:
    """Example background task demonstrating the Celery pattern.

    Args:
        user_id: Optional user ID to process.

    Returns:
        A dict with the task result status.
    """
    logger.info("Running example_task for user_id=%s", user_id)
    return {"status": "completed", "user_id": user_id}
