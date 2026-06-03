"""Add NewsSource kind/category fields; dedupe articles by content_hash."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('news', '0003_fix_news_feed_urls'),
    ]

    operations = [
        migrations.AddField(
            model_name='newssource',
            name='default_category',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='newssource',
            name='kind',
            field=models.CharField(
                choices=[('generic', 'Generic RSS'), ('azores_digest', 'Açores.net daily digest')],
                default='generic',
                max_length=32,
            ),
        ),
        migrations.AlterUniqueTogether(
            name='newsarticle',
            unique_together={('island', 'content_hash')},
        ),
    ]
