"""Register the AzoresBus sync schedules (02 §4.6).

Weekly is the steady state. Late August is daily because upstream is
demonstrably still loading data (2026-07-25 empty, 07-27 populated, 98 B1), and
14 September is the one date where the data — not the code — changes underneath
us, so it gets its own full run.

Follows minibus/migrations/0006_periodic_task_harvest_route_shapes.py.
"""

from django.db import migrations


def _crontab(apps, **fields):
    CrontabSchedule = apps.get_model('django_celery_beat', 'CrontabSchedule')
    defaults = {
        'minute': '0', 'hour': '*', 'day_of_week': '*',
        'day_of_month': '*', 'month_of_year': '*',
    }
    defaults.update(fields)
    schedule, _ = CrontabSchedule.objects.get_or_create(
        **defaults, defaults={'timezone': 'Atlantic/Azores'},
    )
    if schedule.timezone != 'Atlantic/Azores':
        schedule.timezone = 'Atlantic/Azores'
        schedule.save(update_fields=['timezone'])
    return schedule


def register(apps, schema_editor):
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')

    # Sunday 03:30 — the steady state, a full run with the far-season contrast.
    weekly = _crontab(apps, minute='30', hour='3', day_of_week='0')
    PeriodicTask.objects.update_or_create(
        name='azoresbus.sync_schedules.weekly',
        defaults={
            'task': 'azoresbus.sync_schedules',
            'crontab': weekly,
            'enabled': True,
            'kwargs': '{"full": true}',
            'description': 'Full run: near week + far week + holidays.',
        },
    )

    # Daily 03:30 through the changeover window. Incremental: the far week is
    # reused from stored observations, so this is ~1150 requests, not ~2150.
    # Four weeks of daily FULL runs would be ~60,000 requests against a host
    # with no published rate limit.
    daily = _crontab(apps, minute='30', hour='3', month_of_year='8,9')
    PeriodicTask.objects.update_or_create(
        name='azoresbus.sync_schedules.changeover_daily',
        defaults={
            'task': 'azoresbus.sync_schedules',
            'crontab': daily,
            'enabled': True,
            'kwargs': '{"full": false}',
            'description': (
                'Incremental daily through Aug-Sep. Upstream is still loading '
                'data, and 14 September flips 307 from 33 to 38 journeys.'
            ),
        },
    )

    # Tariffs: one 32KB conditional request. Costs nothing when unchanged.
    tariffs = _crontab(apps, minute='0', hour='4')
    PeriodicTask.objects.update_or_create(
        name='azoresbus.sync_tariffs.daily',
        defaults={
            'task': 'azoresbus.sync_tariffs',
            'crontab': tariffs,
            'enabled': True,
            'description': 'Conditional GET on ETag/Last-Modified.',
        },
    )


def unregister(apps, schema_editor):
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')
    PeriodicTask.objects.filter(
        name__in=[
            'azoresbus.sync_schedules.weekly',
            'azoresbus.sync_schedules.changeover_daily',
            'azoresbus.sync_tariffs.daily',
        ]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('azoresbus', '0001_service_calendar'),
        ('django_celery_beat', '__latest__'),
    ]

    operations = [
        migrations.RunPython(register, unregister),
    ]
