"""Register daily trails open-data sync task."""

from django.db import migrations


def _daily_schedule(apps):
    CrontabSchedule = apps.get_model('django_celery_beat', 'CrontabSchedule')
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute='0',
        hour='3',
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
    daily = _daily_schedule(apps)
    PeriodicTask.objects.update_or_create(
        name='trails.sync_open_data',
        defaults={
            'task': 'trails.sync_open_data',
            'crontab': daily,
            'enabled': True,
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ('trails', '0002_poi_source_ref'),
        ('django_celery_beat', '__latest__'),
    ]

    operations = [
        migrations.RunPython(register_sync_task, migrations.RunPython.noop),
    ]
