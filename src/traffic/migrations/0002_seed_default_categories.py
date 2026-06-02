"""Seed default traffic report categories for the São Miguel island.

The quick-pick reporter needs a small, fixed, icon'd set on first launch.
TTL drives auto-expiry; is_schedulable gates the radar scheduling UI.
"""

from django.db import migrations

# (slug, name, icon, default_ttl_minutes, is_schedulable, order)
DEFAULT_CATEGORIES = [
    ('acidente', 'Acidente', '💥', 120, False, 1),
    ('transito', 'Trânsito', '🚗', 60, False, 2),
    ('radar', 'Radar', '📷', 90, True, 3),
    ('policia', 'Polícia', '🚓', 90, False, 4),
    ('obras', 'Obras', '🚧', 1440, False, 5),
    ('desvio', 'Desvio', '↪️', 480, False, 6),
    ('inundacao', 'Inundação', '🌊', 240, False, 7),
    ('perigo', 'Perigo na via', '⚠️', 90, False, 8),
    ('tempo', 'Tempo / Nevoeiro', '🌫️', 180, False, 9),
]


def seed_categories(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    TrafficCategory = apps.get_model('traffic', 'TrafficCategory')
    for island in Island.objects.filter(key='sao-miguel'):
        for slug, name, icon, ttl, schedulable, order in DEFAULT_CATEGORIES:
            TrafficCategory.objects.get_or_create(
                island=island,
                slug=slug,
                defaults={
                    'name': name,
                    'icon': icon,
                    'default_ttl_minutes': ttl,
                    'is_schedulable': schedulable,
                    'order': order,
                },
            )


def remove_categories(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    TrafficCategory = apps.get_model('traffic', 'TrafficCategory')
    slugs = [slug for slug, *_ in DEFAULT_CATEGORIES]
    for island in Island.objects.filter(key='sao-miguel'):
        TrafficCategory.objects.filter(island=island, slug__in=slugs).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('traffic', '0001_initial'),
        ('tenancy', '0009_enable_traffic_feature_flag'),
    ]

    operations = [
        migrations.RunPython(seed_categories, remove_categories),
    ]
