"""Register hourly EMSC sync task."""

from django.db import migrations


def _hourly_schedule(apps):
    CrontabSchedule = apps.get_model('django_celery_beat', 'CrontabSchedule')
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute='0',
        hour='*',
        day_of_week='*',
        day_of_month='*',
        month_of_year='*',
        defaults={'timezone': 'Atlantic/Azores'},
    )
    if schedule.timezone != 'Atlantic/Azores':
        schedule.timezone = 'Atlantic/Azores'
        schedule.save(update_fields=['timezone'])
    return schedule


def register_sync_task(apps, schema_editor):
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')
    hourly = _hourly_schedule(apps)
    PeriodicTask.objects.update_or_create(
        name='seismic.sync_events',
        defaults={
            'task': 'seismic.sync_events',
            'crontab': hourly,
            'enabled': True,
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ('seismic', '0001_initial'),
        ('django_celery_beat', '__latest__'),
    ]

    operations = [
        migrations.RunPython(register_sync_task, migrations.RunPython.noop),
    ]
