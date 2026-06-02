# Generated manually for LegacyImportJob

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('tenancy', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='LegacyImportJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
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
                ('island_key', models.SlugField(default='sao-miguel', max_length=64)),
                ('export_file_path', models.CharField(blank=True, max_length=500)),
                ('legacy_db_url', models.CharField(blank=True, max_length=500)),
                ('skip_steps', models.JSONField(blank=True, default=list)),
                ('current_step', models.CharField(blank=True, max_length=64)),
                ('step_reports', models.JSONField(blank=True, default=list)),
                ('table_counts', models.JSONField(blank=True, null=True)),
                ('celery_task_id', models.CharField(blank=True, max_length=64)),
                ('error', models.TextField(blank=True)),
                ('started_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'verbose_name': 'Legacy import job',
                'verbose_name_plural': 'Legacy import jobs',
                'ordering': ['-started_at'],
            },
        ),
    ]
