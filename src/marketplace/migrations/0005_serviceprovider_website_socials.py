from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("marketplace", "0004_serviceprovider_owner_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="serviceprovider",
            name="website",
            field=models.URLField(blank=True, default="", max_length=300),
        ),
        migrations.AddField(
            model_name="serviceprovider",
            name="socials",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
