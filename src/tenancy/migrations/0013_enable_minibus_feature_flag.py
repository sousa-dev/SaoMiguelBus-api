"""Enable minibus module on sao-miguel."""

from django.db import migrations


def enable_minibus(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    for island in Island.objects.filter(key='sao-miguel'):
        flags = dict(island.feature_flags or {})
        if not flags.get('minibus'):
            flags['minibus'] = True
            island.feature_flags = flags
            island.save(update_fields=['feature_flags'])


class Migration(migrations.Migration):
    dependencies = [
        ('tenancy', '0012_sync_sao_miguel_locales'),
    ]

    operations = [
        migrations.RunPython(enable_minibus, migrations.RunPython.noop),
    ]
