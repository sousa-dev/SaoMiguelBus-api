"""Lengthen default TTLs for long-lived categories.

Construction-driven events (Obras, Desvio) can persist for weeks, so they get a
one-week default. Weather, flooding and road-hazard events get one day. Users can
still override the "valid until" per report, and deny-votes auto-expire stale ones.
"""

from django.db import migrations

# slug -> (new_ttl_minutes, previous_ttl_minutes)
TTL_UPDATES = {
    'obras': (10080, 1440),
    'desvio': (10080, 480),
    'inundacao': (1440, 240),
    'perigo': (1440, 90),
    'tempo': (1440, 180),
}


def _apply(apps, ttl_index):
    TrafficCategory = apps.get_model('traffic', 'TrafficCategory')
    for slug, ttls in TTL_UPDATES.items():
        TrafficCategory.objects.filter(slug=slug).update(default_ttl_minutes=ttls[ttl_index])


def forwards(apps, schema_editor):
    _apply(apps, 0)


def backwards(apps, schema_editor):
    _apply(apps, 1)


class Migration(migrations.Migration):
    dependencies = [
        ('traffic', '0003_periodic_task_run_lifecycle'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
