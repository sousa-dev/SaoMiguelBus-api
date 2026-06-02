"""Trail enrichment fields from Visit Azores."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('trails', '0003_periodic_task_sync_open_data'),
    ]

    operations = [
        migrations.AddField(
            model_name='trail',
            name='shape',
            field=models.CharField(blank=True, default='', max_length=32),
        ),
        migrations.AddField(
            model_name='trail',
            name='duration_min',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='trail',
            name='description_pt',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='trail',
            name='description_en',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='trail',
            name='gpx_url',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
        migrations.AddField(
            model_name='trail',
            name='kml_url',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
        migrations.AddField(
            model_name='trail',
            name='map_image_url',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
        migrations.AddField(
            model_name='trail',
            name='leaflet_url',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
        migrations.AddField(
            model_name='trail',
            name='start_lat',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='trail',
            name='start_lon',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='trail',
            name='waypoints',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
