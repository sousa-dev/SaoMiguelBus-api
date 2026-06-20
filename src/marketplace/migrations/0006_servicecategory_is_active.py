from django.db import migrations, models


def activate_existing_categories(apps, schema_editor):
    ServiceCategory = apps.get_model('marketplace', 'ServiceCategory')
    ServiceCategory.objects.update(is_active=True)


def deactivate_all_categories(apps, schema_editor):
    ServiceCategory = apps.get_model('marketplace', 'ServiceCategory')
    ServiceCategory.objects.update(is_active=False)


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0005_serviceprovider_website_socials'),
    ]

    operations = [
        migrations.AddField(
            model_name='servicecategory',
            name='is_active',
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text='Inactive categories are hidden from public browse/filter UI until staff activates them.',
            ),
        ),
        migrations.RunPython(activate_existing_categories, deactivate_all_categories),
    ]
