"""Add in_app_review_enabled to AppReleaseConfig (default off)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('tenancy', '0014_appreleaseconfig'),
    ]

    operations = [
        migrations.AddField(
            model_name='appreleaseconfig',
            name='in_app_review_enabled',
            field=models.BooleanField(
                default=False,
                help_text='When enabled, native clients may show the store in-app review prompt.',
            ),
        ),
    ]
