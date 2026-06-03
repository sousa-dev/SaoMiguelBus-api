"""Drop ambiguous 'lagoa' term from national-filtered Notícias ao Minuto source."""

from django.db import migrations

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


def remove_lagoa_filter_term(apps, schema_editor):
    NewsSource = apps.get_model('news', 'NewsSource')
    NewsSource.objects.filter(rss_url=NAM_PAIS_RSS).update(filter_terms=AZORES_FILTER_TERMS)


class Migration(migrations.Migration):
    dependencies = [
        ('news', '0007_seed_filtered_sources'),
    ]

    operations = [
        migrations.RunPython(remove_lagoa_filter_term, migrations.RunPython.noop),
    ]
