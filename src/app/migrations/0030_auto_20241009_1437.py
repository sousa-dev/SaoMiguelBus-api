# Generated by Django 3.0.14 on 2024-10-09 14:37

from django.db import migrations
import jsonfield.fields


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0029_auto_20241009_1429'),
    ]

    operations = [
        migrations.AddField(
            model_name='route',
            name='cleaned_stops',
            field=jsonfield.fields.JSONField(default=''),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='trip',
            name='cleaned_stops',
            field=jsonfield.fields.JSONField(default=''),
            preserve_default=False,
        ),
    ]
