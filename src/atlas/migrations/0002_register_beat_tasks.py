"""Register monthly import and daily enrichment as Celery beat tasks."""

from django.db import migrations


def _monthly_schedule(apps):
    CrontabSchedule = apps.get_model('django_celery_beat', 'CrontabSchedule')
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute='0', hour='2', day_of_week='*', day_of_month='1', month_of_year='*',
        defaults={'timezone': 'Atlantic/Azores'},
    )
    if schedule.timezone != 'Atlantic/Azores':
        schedule.timezone = 'Atlantic/Azores'
        schedule.save(update_fields=['timezone'])
    return schedule


def _daily_schedule(apps):
    CrontabSchedule = apps.get_model('django_celery_beat', 'CrontabSchedule')
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute='0', hour='4', day_of_week='*', day_of_month='*', month_of_year='*',
        defaults={'timezone': 'Atlantic/Azores'},
    )
    if schedule.timezone != 'Atlantic/Azores':
        schedule.timezone = 'Atlantic/Azores'
        schedule.save(update_fields=['timezone'])
    return schedule


def register_tasks(apps, schema_editor):
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')
    monthly = _monthly_schedule(apps)
    daily = _daily_schedule(apps)

    PeriodicTask.objects.update_or_create(
        name='atlas.import_all_sources',
        defaults={'task': 'atlas.import_all_sources', 'crontab': monthly, 'enabled': True},
    )
    PeriodicTask.objects.update_or_create(
        name='atlas.enrich_pois',
        defaults={'task': 'atlas.enrich_pois', 'crontab': daily, 'enabled': True},
    )


def unregister_tasks(apps, schema_editor):
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')
    PeriodicTask.objects.filter(name__in=['atlas.import_all_sources', 'atlas.enrich_pois']).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('atlas', '0001_initial'),
        ('django_celery_beat', '__latest__'),
    ]

    operations = [
        migrations.RunPython(register_tasks, unregister_tasks),
    ]
