"""Regression test for a production deploy failure (2026-08-14).

`register()` in azoresbus/migrations/0002_periodic_tasks.py crashed with
`CrontabSchedule.MultipleObjectsReturned` on the tariffs schedule
(minute='0', hour='4', day='*'/'*'/'*'). atlas's enrich_pois task already
registers that exact crontab shape -- sharing it is fine and intended -- but
two rows already existed in production matching those five fields (almost
certainly differing only in `timezone`, which the old lookup could not see),
and `get_or_create()` calls `.get()` internally, which raises the moment more
than one row matches.

Migration modules are not import-statement-friendly (their filenames start
with a digit), so they are loaded via importlib, exactly as Django's own
loader does. The migration functions take a historical `apps` registry; the
real one is a safe stand-in here because CrontabSchedule/PeriodicTask's fields
have not changed shape since this migration was written.
"""

from __future__ import annotations

import importlib

from django.apps import apps as real_apps
from django.test import TestCase
from django_celery_beat.models import CrontabSchedule, PeriodicTask

migration_0002 = importlib.import_module(
    'azoresbus.migrations.0002_periodic_tasks'
)

DUPLICATE_FIELDS = {
    'minute': '0', 'hour': '4', 'day_of_week': '*',
    'day_of_month': '*', 'month_of_year': '*',
}


class PeriodicTasksMigrationDuplicateCrontabTests(TestCase):
    def setUp(self):
        # The production scenario: two rows already share the tariffs
        # crontab's five fields, differing only in timezone.
        CrontabSchedule.objects.create(**DUPLICATE_FIELDS, timezone='UTC')
        CrontabSchedule.objects.create(
            **DUPLICATE_FIELDS, timezone='Atlantic/Azores',
        )

    def test_crontab_helper_does_not_raise_on_duplicates(self):
        schedule = migration_0002._crontab(real_apps, minute='0', hour='4')
        self.assertIsNotNone(schedule)

    def test_crontab_helper_picks_deterministically(self):
        """Same pre-existing state, called twice, must return the same row."""
        first = migration_0002._crontab(real_apps, minute='0', hour='4')
        second = migration_0002._crontab(real_apps, minute='0', hour='4')
        self.assertEqual(first.pk, second.pk)

    def test_no_new_row_is_created_when_matches_already_exist(self):
        before = CrontabSchedule.objects.filter(**DUPLICATE_FIELDS).count()
        migration_0002._crontab(real_apps, minute='0', hour='4')
        after = CrontabSchedule.objects.filter(**DUPLICATE_FIELDS).count()
        self.assertEqual(
            before, after, 'a duplicate-safe lookup must not create a third row',
        )

    def test_register_completes_against_a_duplicate_riddled_database(self):
        """The end-to-end path that actually failed in production."""
        migration_0002.register(real_apps, None)

        self.assertTrue(
            PeriodicTask.objects.filter(
                name='azoresbus.sync_tariffs.daily'
            ).exists()
        )
        self.assertTrue(
            PeriodicTask.objects.filter(
                name='azoresbus.sync_schedules.weekly'
            ).exists()
        )
        self.assertTrue(
            PeriodicTask.objects.filter(
                name='azoresbus.sync_schedules.changeover_daily'
            ).exists()
        )


class PeriodicTasksMigrationCleanDatabaseTests(TestCase):
    """The common case: no pre-existing duplicates. Must keep working."""

    def test_register_creates_exactly_one_row_per_crontab_shape(self):
        migration_0002.register(real_apps, None)

        self.assertEqual(
            CrontabSchedule.objects.filter(**DUPLICATE_FIELDS).count(), 1,
        )

    def test_running_register_twice_is_idempotent(self):
        migration_0002.register(real_apps, None)
        migration_0002.register(real_apps, None)

        self.assertEqual(
            PeriodicTask.objects.filter(
                name='azoresbus.sync_tariffs.daily'
            ).count(),
            1,
        )
        self.assertEqual(
            CrontabSchedule.objects.filter(**DUPLICATE_FIELDS).count(), 1,
        )

    def test_a_shared_crontab_from_another_app_is_reused_not_duplicated(self):
        """atlas's enrich_pois already owns this exact crontab shape.

        atlas/migrations/0002_register_beat_tasks seeds it unconditionally, so
        the test database already has this row before this test body runs --
        no need to create it. Sharing the row is the intended
        django-celery-beat design; the migration must not create a second,
        near-identical row next to it.
        """
        before = list(CrontabSchedule.objects.filter(**DUPLICATE_FIELDS))
        self.assertEqual(
            len(before), 1,
            "expected atlas's migration to have already seeded this row; "
            'if this fails, atlas/migrations/0002 changed shape',
        )
        atlas_row_pk = before[0].pk

        migration_0002.register(real_apps, None)

        after = list(CrontabSchedule.objects.filter(**DUPLICATE_FIELDS))
        self.assertEqual(len(after), 1, 'register() created a duplicate row')
        self.assertEqual(
            after[0].pk, atlas_row_pk,
            "azoresbus's tariffs task must reuse atlas's row, not its own",
        )
