"""Register GDPR Celery Beat periodic tasks (idempotent)."""

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


def _upsert_task(apps, *, name: str, task: str, schedule) -> None:
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')
    PeriodicTask.objects.update_or_create(
        name=name,
        defaults={
            'task': task,
            'crontab': schedule,
            'enabled': True,
        },
    )


def register_gdpr_periodic_tasks(apps, schema_editor):
    daily = _daily_schedule(apps)
    _upsert_task(apps, name='consent.rotate_session_salt', task='consent.rotate_session_salt', schedule=daily)
    _upsert_task(apps, name='consent.expire_consent', task='consent.expire_consent', schedule=daily)
    _upsert_task(apps, name='analytics.anonymize_events', task='analytics.anonymize_events', schedule=daily)


class Migration(migrations.Migration):
    dependencies = [
        ('consent', '0001_initial'),
        ('django_celery_beat', '__latest__'),
    ]

    operations = [
        migrations.RunPython(register_gdpr_periodic_tasks, migrations.RunPython.noop),
    ]
