# Generated by Django 3.0.14 on 2024-10-13 21:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0031_auto_20241009_1445'),
    ]

    operations = [
        migrations.AddField(
            model_name='route',
            name='dislikes',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='route',
            name='likes',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='trip',
            name='dislikes',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='trip',
            name='likes',
            field=models.IntegerField(default=0),
        ),
    ]
