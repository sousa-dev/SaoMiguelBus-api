"""Seed Azores news RSS sources and register hourly poll task."""

from django.db import migrations

DEFAULT_SOURCES = (
    {
        'name': 'Açoriano Oriental',
        'rss_url': 'https://www.acorianooriental.pt/rss/',
        'language': 'pt',
    },
    {
        'name': 'Jornal dos Açores',
        'rss_url': 'https://www.jornaldosacores.com/feed/',
        'language': 'pt',
    },
)


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


def seed_sources_and_beat(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    NewsSource = apps.get_model('news', 'NewsSource')
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')

    island = Island.objects.filter(key='sao-miguel').first()
    if island:
        for row in DEFAULT_SOURCES:
            NewsSource.objects.update_or_create(
                island=island,
                rss_url=row['rss_url'],
                defaults={
                    'name': row['name'],
                    'language': row['language'],
                    'active': True,
                },
            )

    hourly = _hourly_schedule(apps)
    PeriodicTask.objects.update_or_create(
        name='news.poll_sources',
        defaults={
            'task': 'news.poll_sources',
            'crontab': hourly,
            'enabled': True,
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ('news', '0001_initial'),
        ('tenancy', '0005_enable_news_feature_flag'),
        ('django_celery_beat', '__latest__'),
    ]

    operations = [
        migrations.RunPython(seed_sources_and_beat, migrations.RunPython.noop),
    ]
