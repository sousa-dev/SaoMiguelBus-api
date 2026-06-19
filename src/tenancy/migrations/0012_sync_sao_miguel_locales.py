"""Sync sao-miguel locales to the catalogs the mobile app actually ships.

The app intersects bootstrap `island.locales` with its shipped translation
catalogs, so `nl`/`pl` (no catalogs) were silently dropped while `uk`/`zh`
(shipped) never appeared in the picker. Align the list with the 8 shipped
catalogs so the in-app picker and App Store listing match.
"""

from django.db import migrations

SHIPPED_LOCALES = ['pt', 'en', 'de', 'es', 'fr', 'it', 'uk', 'zh']


def sync_locales(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    for island in Island.objects.filter(key='sao-miguel'):
        if island.locales != SHIPPED_LOCALES:
            island.locales = list(SHIPPED_LOCALES)
            island.save(update_fields=['locales'])


class Migration(migrations.Migration):
    dependencies = [
        ('tenancy', '0011_enable_weather_feature_flag'),
    ]

    operations = [
        migrations.RunPython(sync_locales, migrations.RunPython.noop),
    ]
