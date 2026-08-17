"""Widen four island radii so trail geometry actually fits inside island_bbox().

trails.services.feature_in_island() rejects any feature with no coordinate inside the bbox
derived from Island.center_lat/lng + radius_km. The radii seeded in 0017_seed_azores_islands
were rough circles around each island centre, not measured against real content — and the
official Visit Azores trail geometry overruns four of them.

Measured against every trail's full GPX/geofield geometry (max distance from island centre):

    pico          25 km -> needs 32.2   two trails rejected outright today
                                        (calheta-do-nesquim, ponta-da-ilha)
    sao-jorge     20 km -> needs 19.4   passes with no margin at all
    santa-maria   12 km -> needs 13.9   furthest point already outside the box
    flores        12 km -> needs 11.4   thin margin

Terceira (12.8/20), Faial (11.1/15), Graciosa (8.3/10) and Corvo (4.9/6) have comfortable
margins and are left alone. 'sao-miguel' is untouched — it is Hub's own tenant root at 50 km
and carries live transit/traffic data keyed to that radius.

radius_km is also read by traffic.services (in-bounds check for user reports) and
seismic.services (minimum search radius). Neither module is enabled on any of these four
islands, so in practice this migration only moves the trails bbox.
"""

from django.db import migrations

# key -> (previous radius_km, new radius_km). The previous value is asserted before writing
# so this no-ops rather than clobbering a radius someone has since tuned by hand.
RADII = {
    'pico': (25, 35),
    'sao-jorge': (20, 25),
    'santa-maria': (12, 15),
    'flores': (12, 15),
}


def widen_radii(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    for key, (previous, new) in RADII.items():
        Island.objects.filter(key=key, radius_km=previous).update(radius_km=new)


def restore_radii(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    for key, (previous, new) in RADII.items():
        Island.objects.filter(key=key, radius_km=new).update(radius_km=previous)


class Migration(migrations.Migration):
    dependencies = [
        ('tenancy', '0018_seed_sao_miguel_island'),
    ]

    operations = [
        migrations.RunPython(widen_radii, restore_radii),
    ]
