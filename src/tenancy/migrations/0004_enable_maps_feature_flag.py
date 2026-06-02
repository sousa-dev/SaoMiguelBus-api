"""Enable maps feature flag on default island."""

from django.db import migrations


def enable_maps(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    for island in Island.objects.filter(key='sao-miguel'):
        flags = dict(island.feature_flags or {})
        if not flags.get('maps'):
            flags['maps'] = True
            island.feature_flags = flags
            island.save(update_fields=['feature_flags'])


class Migration(migrations.Migration):
    dependencies = [
        ('tenancy', '0003_alter_legacyimportjob_status'),
    ]

    operations = [
        migrations.RunPython(enable_maps, migrations.RunPython.noop),
    ]
