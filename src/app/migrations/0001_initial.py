from django.conf import settings
from django.db import migrations

def create_site(apps, schema_editor):
    Site = apps.get_model('sites', 'Site')
    Site.objects.update_or_create(
        id=1,
        defaults={
            'domain': settings.PROJECT_URL,
            'name': settings.PROJECT_NAME,
        }
    )

class Migration(migrations.Migration):

    dependencies = [
        ('sites', '0002_alter_domain_unique'),  # Ensure this dependency is correct
    ]

    operations = [
        migrations.RunPython(create_site),
    ]