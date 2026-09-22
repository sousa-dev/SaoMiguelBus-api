"""Seed Madeira and Porto Santo parish centers from OSM boundary relations.

Coordinates are forecast sample points. Sé and Santa Cruz are manually placed on
Madeira because their administrative bounding boxes include offshore islands.
"""
import json
from pathlib import Path
from django.db import migrations


def seed(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    Parish = apps.get_model('weather', 'Parish')
    rows = json.loads((Path(__file__).resolve().parent.parent / 'data' / 'parishes_madeira.json').read_text())
    for row in rows:
        island = Island.objects.get(key=row['island'])
        Parish.objects.update_or_create(island=island, slug=row['slug'], defaults={
            'name': row['name'], 'concelho': row['concelho'],
            'latitude': row['lat'], 'longitude': row['lon'], 'is_active': True,
        })


class Migration(migrations.Migration):
    dependencies = [('weather', '0004_fix_vila_franca_parish_coordinates'),
                    ('tenancy', '0021_seed_madeira_islands')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
