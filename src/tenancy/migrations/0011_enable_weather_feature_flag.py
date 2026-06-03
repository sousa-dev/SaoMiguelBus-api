"""Enable weather module on sao-miguel."""

from django.db import migrations


def enable_weather(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    for island in Island.objects.filter(key='sao-miguel'):
        flags = dict(island.feature_flags or {})
        if not flags.get('weather'):
            flags['weather'] = True
            island.feature_flags = flags
            island.save(update_fields=['feature_flags'])


class Migration(migrations.Migration):
    dependencies = [
        ('tenancy', '0010_enable_events_feature_flag'),
    ]

    operations = [
        migrations.RunPython(enable_weather, migrations.RunPython.noop),
    ]
