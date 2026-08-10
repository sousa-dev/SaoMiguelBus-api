"""Seed the 'sao-miguel' Island row itself.

Real bug found running the Azores offline-map app against a fresh environment: every atlas
sync request for São Miguel returned 400 island_required. `TenantMiddleware` resolves
`request.island` by looking up `Island.objects.get(key='sao-miguel')` — and on any environment
where the legacy-import management commands (`migrate_legacy`, `import_legacy`, etc.) were
never run, that row simply doesn't exist. `0016_enable_atlas_feature_flag` and
`0017_seed_azores_islands` both silently no-op on a missing 'sao-miguel' row (0016 filters by
that key and iterates zero rows; 0017's own docstring explicitly — and, it turns out,
incorrectly — assumes something else already created it). This migration is that "something
else," using the exact values `Island.default_sao_miguel()` returns, with `atlas` already
enabled in `feature_flags` so a fresh environment doesn't need 0016 to run again to fix it.
"""

from django.db import migrations

FEATURE_FLAGS = {
    'transit': True,
    'maps': True,
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


def seed_sao_miguel(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    island, created = Island.objects.get_or_create(
        key='sao-miguel',
        defaults={
            'name': 'São Miguel',
            'archipelago': 'Azores',
            'is_live': True,
            'center_lat': 37.782213,
            'center_lng': -25.499806,
            'radius_km': 50,
            'timezone': 'Atlantic/Azores',
            'default_locale': 'pt',
            'locales': ['pt', 'en', 'de', 'es', 'fr', 'it', 'uk', 'zh'],
            'theme': {
                'primaryColor': '#28a745',
                'secondaryColor': '#1e7e34',
                'accentColor': '#ffc107',
            },
            'feature_flags': dict(FEATURE_FLAGS),
        },
    )
    # Row already existed (e.g. created via a legacy-import command) — just make sure atlas
    # is on, same as 0016 intended.
    if not created and not (island.feature_flags or {}).get('atlas'):
        flags = dict(island.feature_flags or {})
        flags['atlas'] = True
        island.feature_flags = flags
        island.save(update_fields=['feature_flags'])


def unseed_sao_miguel(apps, schema_editor):
    # Deliberately a no-op, not a delete: unlike the other eight islands (0017), 'sao-miguel'
    # predates atlas and is Hub's own tenant root — reversing this migration must never risk
    # deleting a real production row full of Hub data.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('tenancy', '0017_seed_azores_islands'),
    ]

    operations = [
        migrations.RunPython(seed_sao_miguel, unseed_sao_miguel),
    ]
