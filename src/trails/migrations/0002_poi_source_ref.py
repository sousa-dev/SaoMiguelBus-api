"""Add source_ref to POI for idempotent open-data sync."""

from django.db import migrations, models


def backfill_poi_source_refs(apps, schema_editor):
    POI = apps.get_model('trails', 'POI')
    for poi in POI.objects.filter(source_ref__isnull=True):
        poi.source_ref = f'legacy-{poi.pk}'
        poi.save(update_fields=['source_ref'])


class Migration(migrations.Migration):
    dependencies = [
        ('trails', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='poi',
            name='source_ref',
            field=models.CharField(max_length=128, null=True),
        ),
        migrations.RunPython(backfill_poi_source_refs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='poi',
            name='source_ref',
            field=models.CharField(max_length=128),
        ),
        migrations.AlterUniqueTogether(
            name='poi',
            unique_together={('island', 'source_ref')},
        ),
    ]
