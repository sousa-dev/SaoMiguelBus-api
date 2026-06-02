"""Seed default service categories for the São Miguel island.

Without categories the listing form has nothing to select and provider
creation rejects unknown slugs, so the module ships with a sensible baseline.
"""

from django.db import migrations

DEFAULT_CATEGORIES = [
    ('transfers', 'Transfers & Táxi', '🚐'),
    ('tours', 'Tours & Excursões', '🗺️'),
    ('guides', 'Guias', '🧭'),
    ('accommodation', 'Alojamento', '🏠'),
    ('activities', 'Atividades', '🤿'),
    ('food', 'Restauração', '🍽️'),
    ('rentals', 'Aluguer', '🚗'),
    ('other', 'Outros', '✨'),
]


def seed_categories(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    ServiceCategory = apps.get_model('marketplace', 'ServiceCategory')
    for island in Island.objects.filter(key='sao-miguel'):
        for slug, name, icon in DEFAULT_CATEGORIES:
            ServiceCategory.objects.get_or_create(
                island=island,
                slug=slug,
                defaults={'name': name, 'icon': icon},
            )


def remove_categories(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    ServiceCategory = apps.get_model('marketplace', 'ServiceCategory')
    slugs = [slug for slug, _, _ in DEFAULT_CATEGORIES]
    for island in Island.objects.filter(key='sao-miguel'):
        ServiceCategory.objects.filter(island=island, slug__in=slugs).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('marketplace', '0001_initial'),
        ('tenancy', '0008_enable_marketplace_feature_flag'),
    ]

    operations = [
        migrations.RunPython(seed_categories, remove_categories),
    ]
