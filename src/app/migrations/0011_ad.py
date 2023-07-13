# Generated by Django 3.0.14 on 2023-07-13 10:05

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0010_variables'),
    ]

    operations = [
        migrations.CreateModel(
            name='Ad',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('entity', models.CharField(max_length=100)),
                ('description', models.CharField(blank=True, max_length=100, null=True)),
                ('media', models.CharField(max_length=1000)),
                ('start', models.DateTimeField()),
                ('end', models.DateTimeField()),
                ('action', models.CharField(blank=True, max_length=100, null=True)),
                ('target', models.CharField(blank=True, max_length=100, null=True)),
                ('status', models.CharField(default='pending', max_length=100)),
            ],
        ),
    ]