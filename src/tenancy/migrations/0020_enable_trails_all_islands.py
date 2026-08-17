"""Enable the trails module on all nine islands.

trails.services._islands_for_sync() filters on feature_flags['trails'], so the nightly
trails.sync_open_data task only ever visited islands carrying that flag. 0017 seeded the eight
non-Hub islands with atlas-only flags, which is why their trails never synced.

This also repairs a latent 'sao-miguel' bug. On a *fresh* environment the ordering is:

    0007_enable_trails_feature_flag  filters key='sao-miguel', matches zero rows, no-ops
                                     (the row does not exist yet — same trap 0018 documents)
    0018_seed_sao_miguel_island      creates the row with trails: False

so any new deploy came up with Hub's own trails sync silently disabled. Existing production is
unaffected either way — its row predates both and already has trails: True.

No Hub app impact: Hub is a single-tenant build that only ever fetches bootstrap for
'sao-miguel', where this flag is already on.
"""

from django.db import migrations


def enable_trails(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    for island in Island.objects.all():
        flags = dict(island.feature_flags or {})
        if flags.get('trails'):
            continue
        flags['trails'] = True
        island.feature_flags = flags
        island.save(update_fields=['feature_flags'])


def disable_trails(apps, schema_editor):
    # Reverses to the 0017 state: the eight atlas islands lose the flag, 'sao-miguel' keeps it
    # because trails predate atlas there and Hub serves them in production.
    Island = apps.get_model('tenancy', 'Island')
    for island in Island.objects.exclude(key='sao-miguel'):
        flags = dict(island.feature_flags or {})
        if not flags.get('trails'):
            continue
        flags['trails'] = False
        island.feature_flags = flags
        island.save(update_fields=['feature_flags'])


class Migration(migrations.Migration):
    dependencies = [
        ('tenancy', '0019_widen_island_radii'),
    ]

    operations = [
        migrations.RunPython(enable_trails, disable_trails),
    ]
