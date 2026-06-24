"""App release config model + seed rows from env defaults."""

from django.db import migrations, models
import django.db.models.deletion


DEFAULT_IOS_VERSION = '5.1.6'
DEFAULT_ANDROID_VERSION = '5.1.6'
DEFAULT_IOS_STORE_URL = 'https://apps.apple.com/pt/app/s%C3%A3o-miguel-bus/id6777066837'
DEFAULT_ANDROID_STORE_URL = (
    'https://play.google.com/store/apps/details?id=com.hsousa_apps.Autocarros'
)


def seed_app_release_configs(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    AppReleaseConfig = apps.get_model('tenancy', 'AppReleaseConfig')
    for island in Island.objects.all():
        AppReleaseConfig.objects.get_or_create(
            island=island,
            defaults={
                'ios_current_version': DEFAULT_IOS_VERSION,
                'android_current_version': DEFAULT_ANDROID_VERSION,
                'ios_update_mode': 'optional',
                'android_update_mode': 'optional',
                'ios_store_url': DEFAULT_IOS_STORE_URL,
                'android_store_url': DEFAULT_ANDROID_STORE_URL,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ('tenancy', '0013_enable_minibus_feature_flag'),
    ]

    operations = [
        migrations.CreateModel(
            name='AppReleaseConfig',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                ('ios_current_version', models.CharField(max_length=32)),
                ('android_current_version', models.CharField(max_length=32)),
                (
                    'ios_update_mode',
                    models.CharField(
                        choices=[('optional', 'Optional'), ('required', 'Required')],
                        default='optional',
                        max_length=16,
                    ),
                ),
                (
                    'android_update_mode',
                    models.CharField(
                        choices=[('optional', 'Optional'), ('required', 'Required')],
                        default='optional',
                        max_length=16,
                    ),
                ),
                ('ios_store_url', models.URLField(max_length=500)),
                ('android_store_url', models.URLField(max_length=500)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'island',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='app_release',
                        to='tenancy.island',
                    ),
                ),
            ],
            options={
                'verbose_name': 'App release config',
                'verbose_name_plural': 'App release configs',
            },
        ),
        migrations.RunPython(seed_app_release_configs, migrations.RunPython.noop),
    ]
