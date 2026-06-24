"""Register periodic minibus route shape harvest task."""

from django.db import migrations


def _service_hours_schedule(apps):
    CrontabSchedule = apps.get_model('django_celery_beat', 'CrontabSchedule')
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute='*/30',
        hour='7-19',
        day_of_week='1-6',
        day_of_month='*',
        month_of_year='*',
        defaults={'timezone': 'Atlantic/Azores'},
    )
    if schedule.timezone != 'Atlantic/Azores':
        schedule.timezone = 'Atlantic/Azores'
        schedule.save(update_fields=['timezone'])
    return schedule


def register_harvest_task(apps, schema_editor):
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')
    schedule = _service_hours_schedule(apps)
    PeriodicTask.objects.update_or_create(
        name='minibus.harvest_route_shapes',
        defaults={
            'task': 'minibus.harvest_route_shapes',
            'crontab': schedule,
            'enabled': True,
        },
    )


def unregister_harvest_task(apps, schema_editor):
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')
    PeriodicTask.objects.filter(name='minibus.harvest_route_shapes').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('minibus', '0005_minibusline_route_shapes'),
        ('django_celery_beat', '__latest__'),
    ]

    operations = [
        migrations.RunPython(register_harvest_task, unregister_harvest_task),
    ]
