"""Cancel all Celery tasks and purge the broker queue."""

from django.core.management.base import BaseCommand

from tenancy.celery_control import cancel_all_celery_work


class Command(BaseCommand):
    help = 'Revoke running Celery tasks, purge the queue, and cancel legacy import jobs'

    def add_arguments(self, parser):
        parser.add_argument(
            '--no-terminate',
            action='store_true',
            help='Revoke without SIGTERM on running worker processes',
        )

    def handle(self, *args, **options):
        result = cancel_all_celery_work(terminate_running=not options['no_terminate'])
        self.stdout.write(
            f"revoked={result['revoked']} purged={result['purged']} "
            f"import_jobs_cancelled={result['import_jobs_cancelled']}"
        )
        if result['task_ids']:
            self.stdout.write('task_ids: ' + ', '.join(result['task_ids']))
