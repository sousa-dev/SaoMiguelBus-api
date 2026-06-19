"""Seed São Miguel Mini Bus catalog from JSON."""

import json
from datetime import date
from pathlib import Path

from django.db import migrations


def seed_catalog(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    MinibusLine = apps.get_model('minibus', 'MinibusLine')
    MinibusTariff = apps.get_model('minibus', 'MinibusTariff')
    MinibusDocument = apps.get_model('minibus', 'MinibusDocument')
    MinibusImportMeta = apps.get_model('minibus', 'MinibusImportMeta')

    island = Island.objects.filter(key='sao-miguel').first()
    if island is None:
        return

    data_path = Path(__file__).resolve().parent.parent / 'data' / 'catalog_sao_miguel.json'
    with data_path.open(encoding='utf-8') as handle:
        catalog = json.load(handle)

    line_by_code = {}
    for row in catalog['lines']:
        line, _ = MinibusLine.objects.update_or_create(
            island=island,
            slug=row['slug'],
            defaults={
                'code': row['code'],
                'name_pt': row['name_pt'],
                'name_en': row['name_en'],
                'color': row['color'],
                'sort_order': row['sort_order'],
                'service_summary': row['service_summary'],
                'is_active': True,
            },
        )
        line_by_code[line.code] = line

    for row in catalog['tariffs']:
        MinibusTariff.objects.update_or_create(
            island=island,
            key=row['key'],
            defaults={
                'label_pt': row['label_pt'],
                'label_en': row['label_en'],
                'price_eur': row['price_eur'],
                'sort_order': row['sort_order'],
                'is_active': True,
            },
        )

    for row in catalog['documents']:
        line = line_by_code.get(row['line_code']) if row.get('line_code') else None
        MinibusDocument.objects.update_or_create(
            island=island,
            slug=row['slug'],
            defaults={
                'title_pt': row['title_pt'],
                'title_en': row['title_en'],
                'doc_type': row['doc_type'],
                'source_filename': row['source_filename'],
                'line_id': line.id if line else None,
                'is_active': True,
            },
        )

    effective_raw = catalog.get('tariffs_effective_date')
    effective_date = date.fromisoformat(effective_raw) if effective_raw else None
    MinibusImportMeta.objects.update_or_create(
        island=island,
        defaults={
            'source_url': catalog.get('source_url', 'https://pdlminibus.pt'),
            'source_revision': '',
            'imported_at': None,
            'tariffs_effective_date': effective_date,
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ('minibus', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_catalog, migrations.RunPython.noop),
    ]
