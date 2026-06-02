"""Queue one-shot feed sync Celery jobs after deploy."""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

FEED_TASKS: tuple[tuple[str, str], ...] = (
    ('news', 'news.poll_sources'),
    ('seismic', 'seismic.sync_events'),
)


class Command(BaseCommand):
    help = 'Queue initial news and seismic feed sync tasks (runs after migrate on deploy).'

    def handle(self, *args: object, **options: object) -> None:
        queued: list[str] = []
        for label, task_name in FEED_TASKS:
            try:
                if label == 'news':
                    from news.tasks import poll_sources_task

                    poll_sources_task.delay()
                elif label == 'seismic':
                    from seismic.tasks import sync_events_task

                    sync_events_task.delay()
                queued.append(task_name)
            except Exception:
                logger.exception('bootstrap_feed_syncs failed to queue %s', task_name)

        if queued:
            self.stdout.write(f'Queued feed sync tasks: {", ".join(queued)}')
        else:
            self.stdout.write('No feed sync tasks were queued (check Celery broker).')
