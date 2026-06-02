"""Register the per-minute traffic lifecycle task (activation + expiry)."""

from django.db import migrations


def _every_minute_schedule(apps):
    CrontabSchedule = apps.get_model('django_celery_beat', 'CrontabSchedule')
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute='*',
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


def register_lifecycle_task(apps, schema_editor):
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')
    every_minute = _every_minute_schedule(apps)
    PeriodicTask.objects.update_or_create(
        name='traffic.run_lifecycle',
        defaults={
            'task': 'traffic.run_lifecycle',
            'crontab': every_minute,
            'enabled': True,
        },
    )


def unregister_lifecycle_task(apps, schema_editor):
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')
    PeriodicTask.objects.filter(name='traffic.run_lifecycle').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('traffic', '0002_seed_default_categories'),
        ('django_celery_beat', '__latest__'),
    ]

    operations = [
        migrations.RunPython(register_lifecycle_task, unregister_lifecycle_task),
    ]
