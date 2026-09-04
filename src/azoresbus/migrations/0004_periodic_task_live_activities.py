"""Register the iOS Live Activity push beat task.

Every minute, matching the cadence `services_trip_live.py` already uses for
the live position itself -- pushing faster would just resend the same numbers
the app's own live poll hasn't refreshed yet.

Follows the `_crontab` reuse-or-create pattern from
azoresbus/migrations/0002_periodic_tasks.py, for the same reason stated there:
`get_or_create()` on `CrontabSchedule` can raise `MultipleObjectsReturned`
against rows that already exist from other apps' tasks.
"""

from django.db import migrations


def _crontab(apps, **fields):
    CrontabSchedule = apps.get_model('django_celery_beat', 'CrontabSchedule')
    defaults = {
        'minute': '*', 'hour': '*', 'day_of_week': '*',
        'day_of_month': '*', 'month_of_year': '*',
    }
    defaults.update(fields)
    schedule = CrontabSchedule.objects.filter(**defaults).order_by('id').first()
    if schedule is None:
        schedule = CrontabSchedule.objects.create(
            **defaults, timezone='Atlantic/Azores',
        )
    elif schedule.timezone != 'Atlantic/Azores':
        schedule.timezone = 'Atlantic/Azores'
        schedule.save(update_fields=['timezone'])
    return schedule


def register(apps, schema_editor):
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')
    every_minute = _crontab(apps)
    PeriodicTask.objects.update_or_create(
        name='azoresbus.push_live_activities',
        defaults={
            'task': 'azoresbus.push_live_activities',
            'crontab': every_minute,
            'enabled': True,
            'description': (
                'Pushes fresh content-state to every registered iOS Live '
                'Activity over APNs. Lock-guarded (PUSH_LOCK_TTL) so a slow '
                'run cannot overlap the next tick.'
            ),
        },
    )


def unregister(apps, schema_editor):
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')
    PeriodicTask.objects.filter(name='azoresbus.push_live_activities').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('azoresbus', '0003_liveactivityregistration'),
        ('django_celery_beat', '__latest__'),
    ]

    operations = [
        migrations.RunPython(register, unregister),
    ]
