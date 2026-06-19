"""Swap network map document from PDF to PNG image."""

from __future__ import annotations

from django.db import migrations


def swap_to_png(apps, schema_editor):
    Document = apps.get_model('minibus', 'MinibusDocument')
    for document in Document.objects.filter(slug='network-map', doc_type='network_map'):
        document.source_filename = 'bus-network.png'
        document.file = ''
        document.save(update_fields=['source_filename', 'file'])


def revert_to_pdf(apps, schema_editor):
    Document = apps.get_model('minibus', 'MinibusDocument')
    for document in Document.objects.filter(slug='network-map', doc_type='network_map'):
        document.source_filename = 'mapa_de_rede.pdf'
        document.file = ''
        document.save(update_fields=['source_filename', 'file'])


class Migration(migrations.Migration):
    dependencies = [
        ('minibus', '0003_swap_line_images'),
    ]

    operations = [
        migrations.RunPython(swap_to_png, revert_to_pdf),
    ]
