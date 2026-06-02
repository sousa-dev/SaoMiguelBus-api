"""Queue one-shot feed sync Celery jobs after deploy."""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand

from shared.feed_syncs import enabled_feed_labels, queue_feed_sync

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Queue initial news, seismic, and trails feed sync tasks (runs after migrate on deploy).'

    def handle(self, *args: object, **options: object) -> None:
        labels = enabled_feed_labels()
        queued: list[str] = []
        for label in labels:
            try:
                info = queue_feed_sync(label)
                queued.append(info['task'])
            except Exception:
                logger.exception('bootstrap_feed_syncs failed to queue %s', label)

        if queued:
            self.stdout.write(
                f'Queued feed sync tasks ({", ".join(labels)}): {", ".join(queued)}',
            )
        else:
            self.stdout.write('No feed sync tasks were queued (check Celery broker).')
