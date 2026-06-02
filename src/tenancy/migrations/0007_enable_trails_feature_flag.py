"""Enable trails module on default island."""

from django.db import migrations


def enable_trails(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    for island in Island.objects.filter(key='sao-miguel'):
        flags = dict(island.feature_flags or {})
        if not flags.get('trails'):
            flags['trails'] = True
            island.feature_flags = flags
            island.save(update_fields=['feature_flags'])


class Migration(migrations.Migration):
    dependencies = [
        ('tenancy', '0006_enable_seismic_feature_flag'),
    ]

    operations = [
        migrations.RunPython(enable_trails, migrations.RunPython.noop),
    ]
