from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('personalization', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='personalizationprofile',
            name='platform',
            field=models.CharField(blank=True, default='', max_length=16),
        ),
    ]
