"""Enable seismic module on default island."""

from django.db import migrations


def enable_seismic(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    for island in Island.objects.filter(key='sao-miguel'):
        flags = dict(island.feature_flags or {})
        if not flags.get('seismic'):
            flags['seismic'] = True
            island.feature_flags = flags
            island.save(update_fields=['feature_flags'])


class Migration(migrations.Migration):
    dependencies = [
        ('tenancy', '0005_enable_news_feature_flag'),
    ]

    operations = [
        migrations.RunPython(enable_seismic, migrations.RunPython.noop),
    ]
