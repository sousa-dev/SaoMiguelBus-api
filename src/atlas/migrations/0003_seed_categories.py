"""Seed the category taxonomy (SDD 07 §3) for every atlas-enabled island."""

import json
from pathlib import Path

from django.db import migrations


def seed_categories(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    AtlasCategory = apps.get_model('atlas', 'AtlasCategory')

    data_path = Path(__file__).resolve().parent.parent / 'data' / 'categories.json'
    with data_path.open(encoding='utf-8') as handle:
        categories = json.load(handle)

    islands = Island.objects.filter(feature_flags__atlas=True)
    for island in islands:
        for row in categories:
            AtlasCategory.objects.update_or_create(
                island=island,
                slug=row['slug'],
                defaults={
                    'name': row['name'],
                    'group': row['group'],
                    'icon': row['icon'],
                    'color': row['color'],
                    'sort_order': row['sort_order'],
                    'is_safety_critical': row['is_safety_critical'],
                    'is_active': True,
                },
            )


def unseed_categories(apps, schema_editor):
    AtlasCategory = apps.get_model('atlas', 'AtlasCategory')
    data_path = Path(__file__).resolve().parent.parent / 'data' / 'categories.json'
    with data_path.open(encoding='utf-8') as handle:
        slugs = [row['slug'] for row in json.load(handle)]
    AtlasCategory.objects.filter(slug__in=slugs).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('atlas', '0002_register_beat_tasks'),
        ('tenancy', '0017_seed_azores_islands'),
    ]

    operations = [
        migrations.RunPython(seed_categories, unseed_categories),
    ]
