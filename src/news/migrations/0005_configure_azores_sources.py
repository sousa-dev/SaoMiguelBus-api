"""Configure Azores news sources for digest splitting and purge legacy blobs."""

from django.db import migrations

ALRA_RSS = 'https://xn--aores-yra.net/rss/alra.xml'
JORAA_RSS = 'https://xn--aores-yra.net/rss/joraa.xml'


def configure_azores_sources(apps, schema_editor):
    NewsSource = apps.get_model('news', 'NewsSource')
    NewsArticle = apps.get_model('news', 'NewsArticle')

    alra = NewsSource.objects.filter(rss_url=ALRA_RSS).first()
    if alra:
        alra.kind = 'azores_digest'
        alra.default_category = 'noticias'
        alra.save(update_fields=['kind', 'default_category'])
        NewsArticle.objects.filter(source=alra).delete()

    joraa = NewsSource.objects.filter(rss_url=JORAA_RSS).first()
    if joraa:
        joraa.kind = 'azores_digest'
        joraa.default_category = 'pagamentos'
        joraa.save(update_fields=['kind', 'default_category'])
        NewsArticle.objects.filter(source=joraa).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('news', '0004_news_split_schema'),
    ]

    operations = [
        migrations.RunPython(configure_azores_sources, migrations.RunPython.noop),
    ]
