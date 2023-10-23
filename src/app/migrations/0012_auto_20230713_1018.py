# Generated by Django 3.0.14 on 2023-07-13 10:18

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0011_ad'),
    ]

    operations = [
        migrations.AddField(
            model_name='ad',
            name='advertise_on',
            field=models.CharField(default='home', max_length=100),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='ad',
            name='platform',
            field=models.CharField(blank=True, choices=[('android', 'Android'), ('ios', 'iOS'), ('web', 'Web')], max_length=100),
        ),
    ]
