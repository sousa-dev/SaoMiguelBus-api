# Generated by Django 3.0.14 on 2024-10-19 19:07

from django.db import migrations
import jsonfield.fields


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0033_aifeedback'),
    ]

    operations = [
        migrations.AlterField(
            model_name='info',
            name='message',
            field=jsonfield.fields.JSONField(),
        ),
        migrations.AlterField(
            model_name='info',
            name='title',
            field=jsonfield.fields.JSONField(),
        ),
    ]
