"""Add national_filtered source kind, filter_terms, and max_items_per_poll."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('news', '0005_configure_azores_sources'),
    ]

    operations = [
        migrations.AddField(
            model_name='newssource',
            name='filter_terms',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='newssource',
            name='max_items_per_poll',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='newssource',
            name='kind',
            field=models.CharField(
                choices=[
                    ('generic', 'Generic RSS'),
                    ('azores_digest', 'Açores.net daily digest'),
                    ('national_filtered', 'National RSS, Azores-filtered'),
                ],
                default='generic',
                max_length=32,
            ),
        ),
    ]
