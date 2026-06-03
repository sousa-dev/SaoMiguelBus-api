"""Seed RTP Notícias País as national-filtered (no dedicated Açores RSS exists)."""

from django.db import migrations

RTP_PAIS_RSS = 'https://www.rtp.pt/noticias/rss/pais'

# Keep in sync with news.azores_filter_terms.AZORES_FILTER_TERMS
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


def seed_rtp_noticias_pais(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    NewsSource = apps.get_model('news', 'NewsSource')

    island = Island.objects.filter(key='sao-miguel').first()
    if not island:
        return

    NewsSource.objects.update_or_create(
        island=island,
        rss_url=RTP_PAIS_RSS,
        defaults={
            'name': 'RTP Notícias (País)',
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
        ('news', '0008_remove_lagoa_filter_term'),
    ]

    operations = [
        migrations.RunPython(seed_rtp_noticias_pais, migrations.RunPython.noop),
    ]
