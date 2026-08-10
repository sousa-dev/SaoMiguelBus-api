"""Seed Island tenant rows for the eight Azores islands atlas needs beyond sao-miguel (D14).

Hub only ever created 'sao-miguel'. Atlas is multi-island from launch, and every atlas row is
TenantScopedModel — it needs a real Island row to hang off. These rows carry `atlas: True` only;
every Hub-specific flag stays False, since Hub itself remains São Miguel-only. `is_live=True` so
TenantMiddleware will actually serve requests scoped to them (see tenancy/middleware.py).
"""

from django.db import migrations

ISLANDS = [
    {
        'key': 'santa-maria', 'name': 'Santa Maria',
        'center_lat': 36.9714, 'center_lng': -25.1700, 'radius_km': 12,
    },
    {
        'key': 'terceira', 'name': 'Terceira',
        'center_lat': 38.7169, 'center_lng': -27.2225, 'radius_km': 20,
    },
    {
        'key': 'graciosa', 'name': 'Graciosa',
        'center_lat': 39.0892, 'center_lng': -28.0069, 'radius_km': 10,
    },
    {
        'key': 'sao-jorge', 'name': 'São Jorge',
        'center_lat': 38.6667, 'center_lng': -28.0833, 'radius_km': 20,
    },
    {
        'key': 'pico', 'name': 'Pico',
        'center_lat': 38.4655, 'center_lng': -28.3990, 'radius_km': 25,
    },
    {
        'key': 'faial', 'name': 'Faial',
        'center_lat': 38.5825, 'center_lng': -28.7000, 'radius_km': 15,
    },
    {
        'key': 'flores', 'name': 'Flores',
        'center_lat': 39.4556, 'center_lng': -31.1319, 'radius_km': 12,
    },
    {
        'key': 'corvo', 'name': 'Corvo',
        'center_lat': 39.6711, 'center_lng': -31.1136, 'radius_km': 6,
    },
]

# Same skeleton as Island.default_sao_miguel()['feature_flags'], atlas-only.
FEATURE_FLAGS = {
    'transit': False,
    'maps': False,
    'news': False,
    'seismic': False,
    'marketplace': False,
    'trails': False,
    'traffic': False,
    'events': False,
    'weather': False,
    'minibus': False,
    'atlas': True,
}


def seed_islands(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    for row in ISLANDS:
        Island.objects.get_or_create(
            key=row['key'],
            defaults={
                'name': row['name'],
                'archipelago': 'Azores',
                'is_live': True,
                'center_lat': row['center_lat'],
                'center_lng': row['center_lng'],
                'radius_km': row['radius_km'],
                'timezone': 'Atlantic/Azores',
                'default_locale': 'pt',
                'locales': ['pt', 'en', 'de', 'es', 'fr', 'it', 'uk', 'zh'],
                'theme': {},
                'feature_flags': dict(FEATURE_FLAGS),
            },
        )


def unseed_islands(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    Island.objects.filter(key__in=[row['key'] for row in ISLANDS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('tenancy', '0016_enable_atlas_feature_flag'),
    ]

    operations = [
        migrations.RunPython(seed_islands, unseed_islands),
    ]
