"""Add route_shapes JSONField to MinibusLine."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('minibus', '0004_swap_network_map_image'),
    ]

    operations = [
        migrations.AddField(
            model_name='minibusline',
            name='route_shapes',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
