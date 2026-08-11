"""Correct two São Miguel parish coordinates that were seeded ~500 km off.

`Ponta Garça` and `Ribeira das Tainhas` were both seeded at 33.183586, -25.218542 — the same
value for both rows, and a latitude that puts them in open ocean roughly 500 km south of São
Miguel. Open-Meteo answered for that point quite happily, so the API served plausible-looking
numbers for the wrong place, and any nearest-parish matching skipped these two entirely.

Coordinates below are the settlement centres from OpenStreetMap, matching how the rest of the
seed file is built (village nodes, not administrative centroids).
"""

from django.db import migrations

CORRECTIONS = {
    'ponta-garca-vila-franca-do-campo': (37.717011, -25.372928),
    'ribeira-das-tainhas-vila-franca-do-campo': (37.717864, -25.411201),
}

# What the rows were seeded with — used to scope the reverse, and to avoid overwriting a
# coordinate someone has since corrected by hand.
BROKEN = (33.183586, -25.218542)


def fix_coordinates(apps, schema_editor):
    Parish = apps.get_model('weather', 'Parish')
    for slug, (latitude, longitude) in CORRECTIONS.items():
        Parish.objects.filter(
            slug=slug,
            latitude=BROKEN[0],
            longitude=BROKEN[1],
        ).update(latitude=latitude, longitude=longitude)


def restore_coordinates(apps, schema_editor):
    Parish = apps.get_model('weather', 'Parish')
    for slug, (latitude, longitude) in CORRECTIONS.items():
        Parish.objects.filter(slug=slug, latitude=latitude, longitude=longitude).update(
            latitude=BROKEN[0],
            longitude=BROKEN[1],
        )


class Migration(migrations.Migration):
    dependencies = [
        ('weather', '0003_parishproximity'),
    ]

    operations = [
        migrations.RunPython(fix_coordinates, restore_coordinates),
    ]
