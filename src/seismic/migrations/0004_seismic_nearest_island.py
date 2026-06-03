"""Add nearest-island fields and backfill from epicentre coordinates."""

from __future__ import annotations

from django.db import migrations, models


def backfill_nearest_island(apps, schema_editor):
    SeismicEvent = apps.get_model('seismic', 'SeismicEvent')
    from seismic.data import compute_nearest_fields

    for event in SeismicEvent.objects.iterator():
        fields = compute_nearest_fields(event.latitude, event.longitude)
        for name, value in fields.items():
            setattr(event, name, value)
        event.save(
            update_fields=[
                'nearest_island_key',
                'nearest_island_name',
                'nearest_island_distance_km',
                'nearest_island_bearing',
            ],
        )


class Migration(migrations.Migration):
    dependencies = [
        ('seismic', '0003_feltreport_felt'),
    ]

    operations = [
        migrations.AddField(
            model_name='seismicevent',
            name='nearest_island_key',
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.AddField(
            model_name='seismicevent',
            name='nearest_island_name',
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name='seismicevent',
            name='nearest_island_distance_km',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='seismicevent',
            name='nearest_island_bearing',
            field=models.CharField(blank=True, max_length=4, null=True),
        ),
        migrations.RunPython(backfill_nearest_island, migrations.RunPython.noop),
    ]
