"""Enable atlas module on sao-miguel."""

from django.db import migrations


def enable_atlas(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    for island in Island.objects.filter(key='sao-miguel'):
        flags = dict(island.feature_flags or {})
        if not flags.get('atlas'):
            flags['atlas'] = True
            island.feature_flags = flags
            island.save(update_fields=['feature_flags'])


class Migration(migrations.Migration):
    dependencies = [
        ('tenancy', '0015_appreleaseconfig_in_app_review_enabled'),
    ]

    operations = [
        migrations.RunPython(enable_atlas, migrations.RunPython.noop),
    ]
