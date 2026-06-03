"""Seed São Miguel parishes and register hourly weather refresh."""

import json
from pathlib import Path

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


def seed_parishes_and_beat(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    Parish = apps.get_model('weather', 'Parish')
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')

    island = Island.objects.filter(key='sao-miguel').first()
    if island:
        data_path = Path(__file__).resolve().parent.parent / 'data' / 'parishes_sao_miguel.json'
        with data_path.open(encoding='utf-8') as handle:
            rows = json.load(handle)
        for row in rows:
            Parish.objects.update_or_create(
                island=island,
                slug=row['slug'],
                defaults={
                    'name': row['name'],
                    'concelho': row['concelho'],
                    'latitude': row['lat'],
                    'longitude': row['lon'],
                    'is_active': True,
                },
            )

    hourly = _hourly_schedule(apps)
    PeriodicTask.objects.update_or_create(
        name='weather.refresh_forecasts',
        defaults={
            'task': 'weather.refresh_forecasts',
            'crontab': hourly,
            'enabled': True,
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ('weather', '0001_initial'),
        ('tenancy', '0001_initial'),
        ('django_celery_beat', '__latest__'),
    ]

    operations = [
        migrations.RunPython(seed_parishes_and_beat, migrations.RunPython.noop),
    ]
