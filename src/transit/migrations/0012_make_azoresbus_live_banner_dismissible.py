"""Let riders dismiss the "new timetables are live" banner for good.

0008 seeded this banner with `dismissible: False` deliberately, on the theory
that a rider needs to actually take in a dated changeover announcement. The
app has since grown a chip fallback (Info icon + short caption) that keeps the
banner reachable after dismissal, so a permanent "got it" no longer means the
notice vanishes without a trace -- it just stops demanding full-size real
estate. Flipping this one field is the whole rollout: the app already renders
the X and persists the choice whenever the server allows it.

Only touches the field if it is still exactly what 0008 seeded, so an
operator's later edit -- including a deliberate `dismissible: False` -- is
left alone.
"""

from django.db import migrations

ISLAND_KEY = 'sao-miguel'
BANNER_ID = 'azoresbus-live-2026-09'


def make_dismissible(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    island = Island.objects.filter(key=ISLAND_KEY).first()
    if island is None:
        return
    flags = dict(island.feature_flags or {})
    azoresbus = dict(flags.get('azoresbus') or {})
    banner = dict(azoresbus.get('banner') or {})
    if banner.get('id') != BANNER_ID or banner.get('dismissible') is not False:
        return
    banner['dismissible'] = True
    azoresbus['banner'] = banner
    flags['azoresbus'] = azoresbus
    island.feature_flags = flags
    island.save(update_fields=['feature_flags'])


def make_undismissible(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    island = Island.objects.filter(key=ISLAND_KEY).first()
    if island is None:
        return
    flags = dict(island.feature_flags or {})
    azoresbus = dict(flags.get('azoresbus') or {})
    banner = dict(azoresbus.get('banner') or {})
    if banner.get('id') != BANNER_ID or banner.get('dismissible') is not True:
        return
    banner['dismissible'] = False
    azoresbus['banner'] = banner
    flags['azoresbus'] = azoresbus
    island.feature_flags = flags
    island.save(update_fields=['feature_flags'])


class Migration(migrations.Migration):

    dependencies = [
        ('transit', '0011_stop_cleaned_name_unique'),
        ('tenancy', '0018_seed_sao_miguel_island'),
    ]

    operations = [
        migrations.RunPython(make_dismissible, make_undismissible),
    ]
