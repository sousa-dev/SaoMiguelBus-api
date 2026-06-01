# Generated manually for LegacyExportJob

from django.db import migrations, models
import django.utils.timezone
import jsonfield.fields


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0037_emailopen'),
    ]

    operations = [
        migrations.CreateModel(
            name='LegacyExportJob',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('job_id', models.CharField(editable=False, max_length=32, unique=True)),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('running', 'Running'),
                        ('completed', 'Completed'),
                        ('failed', 'Failed'),
                    ],
                    default='pending',
                    max_length=20,
                )),
                ('started_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('exported_at', models.DateTimeField(blank=True, null=True)),
                ('export_file', models.FileField(blank=True, upload_to='legacy_exports/')),
                ('table_counts', jsonfield.fields.JSONField(blank=True, null=True)),
                ('error', models.TextField(blank=True)),
            ],
            options={
                'verbose_name': 'Legacy export job',
                'verbose_name_plural': 'Legacy export jobs',
                'ordering': ['-started_at'],
            },
        ),
    ]
