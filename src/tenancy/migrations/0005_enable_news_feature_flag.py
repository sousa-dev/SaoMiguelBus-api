"""Enable news module on default island."""

from django.db import migrations


def enable_news(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    for island in Island.objects.filter(key='sao-miguel'):
        flags = dict(island.feature_flags or {})
        if not flags.get('news'):
            flags['news'] = True
            island.feature_flags = flags
            island.save(update_fields=['feature_flags'])


class Migration(migrations.Migration):
    dependencies = [
        ('tenancy', '0004_enable_maps_feature_flag'),
    ]

    operations = [
        migrations.RunPython(enable_news, migrations.RunPython.noop),
    ]
