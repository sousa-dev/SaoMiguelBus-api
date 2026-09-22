"""Add the four Madeira Offline Map regions without changing Azores tenants."""
from django.db import migrations

REGIONS = (
    ('madeira', 'Madeira', 32.75, -16.98, 45, True),
    ('porto-santo', 'Porto Santo', 33.06, -16.34, 13, True),
    ('desertas', 'Ilhas Desertas', 32.53, -16.54, 24, False),
    ('selvagens', 'Ilhas Selvagens', 30.10, -15.94, 23, False),
)


def seed(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    for key, name, lat, lon, radius, visitor in REGIONS:
        Island.objects.get_or_create(key=key, defaults={
            'name': name, 'archipelago': 'Madeira', 'is_live': True,
            'center_lat': lat, 'center_lng': lon, 'radius_km': radius,
            'timezone': 'Atlantic/Madeira', 'default_locale': 'pt',
            'locales': ['pt', 'en', 'de', 'es', 'fr', 'it'],
            'theme': {'primaryColor': '#003DA5', 'secondaryColor': '#D22630', 'accentColor': '#FFCC00'},
            'feature_flags': {'atlas': True, 'trails': visitor, 'weather': visitor,
                              'transit': False, 'maps': False, 'news': False, 'seismic': False,
                              'marketplace': False, 'traffic': False, 'events': False, 'minibus': False},
        })


class Migration(migrations.Migration):
    dependencies = [('tenancy', '0020_enable_trails_all_islands')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
