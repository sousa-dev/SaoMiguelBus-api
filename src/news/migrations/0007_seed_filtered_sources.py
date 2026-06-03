"""Seed Azores gov press and national-filtered Notícias ao Minuto sources."""

from django.db import migrations

GOV_NOTAS_RSS = (
    'https://portal.azores.gov.pt/web/comunicacao/rss/-/asset_publisher/0WEMSOVhE63P/rss'
)
NAM_PAIS_RSS = 'https://www.noticiasaominuto.com/rss/pais'

AZORES_FILTER_TERMS = [
    'acores',
    'sao miguel',
    'santa maria',
    'terceira',
    'graciosa',
    'sao jorge',
    'pico',
    'faial',
    'flores',
    'corvo',
    'ponta delgada',
    'ribeira grande',
    'vila franca do campo',
    'nordeste',
    'povoacao',
    'angra do heroismo',
    'praia da vitoria',
    'horta',
    'velas',
    'madalena',
    'lajes',
    'santa cruz',
]


def seed_filtered_sources(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    NewsSource = apps.get_model('news', 'NewsSource')

    island = Island.objects.filter(key='sao-miguel').first()
    if not island:
        return

    # Portal returns HTML to feedparser today; keep inactive until RSS XML is confirmed.
    NewsSource.objects.update_or_create(
        island=island,
        rss_url=GOV_NOTAS_RSS,
        defaults={
            'name': 'Governo dos Açores (Notas Informativas)',
            'language': 'pt',
            'active': False,
            'kind': 'generic',
            'default_category': 'governo',
            'filter_terms': [],
            'max_items_per_poll': 0,
        },
    )

    NewsSource.objects.update_or_create(
        island=island,
        rss_url=NAM_PAIS_RSS,
        defaults={
            'name': 'Notícias ao Minuto (País)',
            'language': 'pt',
            'active': True,
            'kind': 'national_filtered',
            'default_category': '',
            'filter_terms': AZORES_FILTER_TERMS,
            'max_items_per_poll': 10,
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ('news', '0006_news_national_filtered'),
        ('tenancy', '0005_enable_news_feature_flag'),
    ]

    operations = [
        migrations.RunPython(seed_filtered_sources, migrations.RunPython.noop),
    ]
