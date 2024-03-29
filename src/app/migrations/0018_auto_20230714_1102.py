# Generated by Django 3.0.14 on 2023-07-14 11:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0017_auto_20230713_2223'),
    ]

    operations = [
        migrations.AddField(
            model_name='ad',
            name='clicked',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='ad',
            name='action',
            field=models.CharField(blank=True, choices=[('open', 'Open URL'), ('directions', 'Get Directions To'), ('call', 'Call To Number'), ('sms', 'Send SMS'), ('email', 'Send Email'), ('whatsapp', 'Send WhatsApp Message'), ('share', 'Share')], max_length=100, null=True),
        ),
    ]
