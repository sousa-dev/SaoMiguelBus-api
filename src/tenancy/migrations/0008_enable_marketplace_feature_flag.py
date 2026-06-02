"""Enable marketplace module on default island."""

from django.db import migrations


def enable_marketplace(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    for island in Island.objects.filter(key='sao-miguel'):
        flags = dict(island.feature_flags or {})
        if not flags.get('marketplace'):
            flags['marketplace'] = True
            island.feature_flags = flags
            island.save(update_fields=['feature_flags'])


class Migration(migrations.Migration):
    dependencies = [
        ('tenancy', '0007_enable_trails_feature_flag'),
    ]

    operations = [
        migrations.RunPython(enable_marketplace, migrations.RunPython.noop),
    ]
