# Replace AlterField (bigint FK -> jsonb fails on Postgres) with drop + add.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transit', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='trip',
            name='information',
        ),
        migrations.AddField(
            model_name='trip',
            name='information',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
