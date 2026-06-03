from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("marketplace", "0003_servicecategory_user_suggested"),
    ]

    operations = [
        migrations.AddField(
            model_name="serviceprovider",
            name="claimed_owner",
            field=models.BooleanField(
                default=False,
                help_text="Submitter declared they are the business owner.",
            ),
        ),
        migrations.AddField(
            model_name="serviceprovider",
            name="internal_email",
            field=models.EmailField(
                blank=True,
                default="",
                help_text="Owner contact for SMB Hub staff only; not shown on public listings.",
            ),
        ),
        migrations.AddField(
            model_name="serviceprovider",
            name="internal_phone",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Owner contact for SMB Hub staff only; not shown on public listings.",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="serviceprovider",
            name="verified_by_owner",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="Staff-confirmed business ownership; set only in Django admin.",
            ),
        ),
    ]
