"""Swap per-line timetable documents from PDF to PNG images.

Updates existing rows so the bundled PNG fallback serves correctly even
before the next `import_minibus` re-copies binaries into MEDIA_ROOT.
"""

from __future__ import annotations

from django.db import migrations

LINE_IMAGES = {
    'line-a': 'line-a.png',
    'line-b': 'line-b.png',
    'line-c': 'line-c.png',
    'line-d': 'line-d.png',
}


def swap_to_png(apps, schema_editor):
    Document = apps.get_model('minibus', 'MinibusDocument')
    for slug, filename in LINE_IMAGES.items():
        for document in Document.objects.filter(slug=slug, doc_type='timetable'):
            document.source_filename = filename
            # Drop the stale PDF reference; bundled PNG fallback (data/source) takes over
            # until the next import_minibus re-attaches the file in MEDIA_ROOT.
            document.file = ''
            document.save(update_fields=['source_filename', 'file'])


def revert_to_pdf(apps, schema_editor):
    Document = apps.get_model('minibus', 'MinibusDocument')
    pdf_names = {
        'line-a': 'A - LINHA A - AMARELA.pdf',
        'line-b': 'B - LINHA B - VERDE.pdf',
        'line-c': 'C - LINHA C - AZUL.pdf',
        'line-d': 'D - LINHA D - LARANJA.pdf',
    }
    for slug, filename in pdf_names.items():
        for document in Document.objects.filter(slug=slug, doc_type='timetable'):
            document.source_filename = filename
            document.file = ''
            document.save(update_fields=['source_filename', 'file'])


class Migration(migrations.Migration):
    dependencies = [
        ('minibus', '0002_seed_catalog'),
    ]

    operations = [
        migrations.RunPython(swap_to_png, revert_to_pdf),
    ]
