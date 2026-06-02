"""Replace broken seed RSS URLs with working Azores feeds."""

from django.db import migrations

# Verified 2026-06: alra/joraa return 200 + entries; old AO/jornaldosacores URLs were 404/DNS fail.
SOURCE_UPDATES = (
    {
        'old_url': 'https://www.acorianooriental.pt/rss/',
        'rss_url': 'https://xn--aores-yra.net/rss/alra.xml',
        'name': 'ALRA (Açores)',
        'language': 'pt',
    },
    {
        'old_url': 'https://www.jornaldosacores.com/feed/',
        'rss_url': 'https://xn--aores-yra.net/rss/joraa.xml',
        'name': 'JORAA (Açores)',
        'language': 'pt',
    },
)


def fix_feed_urls(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    NewsSource = apps.get_model('news', 'NewsSource')

    island = Island.objects.filter(key='sao-miguel').first()
    if not island:
        return

    for row in SOURCE_UPDATES:
        updated = NewsSource.objects.filter(island=island, rss_url=row['old_url']).update(
            rss_url=row['rss_url'],
            name=row['name'],
            language=row['language'],
            active=True,
        )
        if not updated:
            NewsSource.objects.update_or_create(
                island=island,
                rss_url=row['rss_url'],
                defaults={
                    'name': row['name'],
                    'language': row['language'],
                    'active': True,
                },
            )


class Migration(migrations.Migration):
    dependencies = [
        ('news', '0002_seed_sources_and_beat'),
    ]

    operations = [
        migrations.RunPython(fix_feed_urls, migrations.RunPython.noop),
    ]
