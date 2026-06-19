"""Mini Bus catalog seeding and API helpers."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.utils import timezone

from minibus.models import MinibusDocument, MinibusImportMeta, MinibusLine, MinibusTariff
from tenancy.models import Island

SOURCE_URL = 'https://pdlminibus.pt'
ATTRIBUTION = 'Schedules and fares sourced from pdlminibus.pt'


def default_source_dir() -> Path:
    override = os.environ.get('MINIBUS_SOURCE_DIR', '').strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / 'data' / 'source'


def bundled_document_path(document: MinibusDocument) -> Path | None:
    if not document.source_filename:
        return None
    path = default_source_dir() / document.source_filename
    return path if path.is_file() else None


def document_is_available(document: MinibusDocument | None) -> bool:
    if document is None:
        return False
    if document.file:
        return True
    return bundled_document_path(document) is not None


def open_document_file(document: MinibusDocument):
    """Return (file_handle, content_type, filename). Caller must close the handle."""
    import mimetypes

    if document.file:
        content_type, _ = mimetypes.guess_type(document.file.name)
        if content_type is None:
            content_type = 'application/octet-stream'
        return document.file.open('rb'), content_type, document.source_filename

    bundled = bundled_document_path(document)
    if bundled is None:
        raise FileNotFoundError(document.slug)

    content_type, _ = mimetypes.guess_type(bundled.name)
    if content_type is None:
        content_type = 'application/octet-stream'
    return bundled.open('rb'), content_type, document.source_filename


def catalog_path() -> Path:
    return Path(__file__).resolve().parent / 'data' / 'catalog_sao_miguel.json'


def load_catalog() -> dict[str, Any]:
    with catalog_path().open(encoding='utf-8') as handle:
        return json.load(handle)


def seed_catalog(island: Island) -> dict[str, int]:
    """Upsert lines, tariffs, and document rows from JSON (no binary files)."""
    catalog = load_catalog()
    line_by_code: dict[str, MinibusLine] = {}

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

    tariff_count = 0
    for row in catalog['tariffs']:
        MinibusTariff.objects.update_or_create(
            island=island,
            key=row['key'],
            defaults={
                'label_pt': row['label_pt'],
                'label_en': row['label_en'],
                'price_eur': Decimal(row['price_eur']),
                'sort_order': row['sort_order'],
                'is_active': True,
            },
        )
        tariff_count += 1

    document_count = 0
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
                'line': line,
                'is_active': True,
            },
        )
        document_count += 1

    effective = catalog.get('tariffs_effective_date')
    effective_date = date.fromisoformat(effective) if effective else None
    MinibusImportMeta.objects.update_or_create(
        island=island,
        defaults={
            'source_url': catalog.get('source_url', SOURCE_URL),
            'source_revision': '',
            'imported_at': None,
            'tariffs_effective_date': effective_date,
        },
    )

    return {
        'lines': len(line_by_code),
        'tariffs': tariff_count,
        'documents': document_count,
    }


def get_import_meta(island: Island) -> MinibusImportMeta | None:
    return MinibusImportMeta.objects.filter(island=island).first()


def build_meta_payload(island: Island) -> dict[str, Any]:
    meta = get_import_meta(island)
    return {
        'attribution': ATTRIBUTION,
        'source_url': meta.source_url if meta else SOURCE_URL,
        'imported_at': meta.imported_at.isoformat() if meta and meta.imported_at else None,
        'tariffs_effective_date': (
            meta.tariffs_effective_date.isoformat()
            if meta and meta.tariffs_effective_date
            else None
        ),
        'source_revision': meta.source_revision if meta else '',
    }


def pick_bilingual_text(*, pt: str, en: str, locale: str) -> str:
    """Catalog is PT + EN only: Portuguese app locale, English for all others."""
    return pt if locale.startswith('pt') else en


def serialize_line(line: MinibusLine, *, locale: str, request) -> dict[str, Any]:
    name = pick_bilingual_text(pt=line.name_pt, en=line.name_en, locale=locale)
    timetable = line.documents.filter(doc_type=MinibusDocument.DOC_TIMETABLE, is_active=True).first()
    return {
        'code': line.code,
        'slug': line.slug,
        'name': name,
        'color': line.color,
        'sort_order': line.sort_order,
        'service_summary': line.service_summary,
        'timetable_slug': timetable.slug if timetable else None,
        'timetable_file_url': document_file_url(request, timetable) if timetable else None,
    }


def serialize_tariff(tariff: MinibusTariff, *, locale: str) -> dict[str, Any]:
    label = pick_bilingual_text(pt=tariff.label_pt, en=tariff.label_en, locale=locale)
    return {
        'key': tariff.key,
        'label': label,
        'price_eur': str(tariff.price_eur),
        'sort_order': tariff.sort_order,
    }


def serialize_document(document: MinibusDocument, *, locale: str, request) -> dict[str, Any]:
    title = pick_bilingual_text(pt=document.title_pt, en=document.title_en, locale=locale)
    return {
        'slug': document.slug,
        'title': title,
        'doc_type': document.doc_type,
        'line_code': document.line.code if document.line_id else None,
        'file_url': document_file_url(request, document),
        'has_file': document_is_available(document),
    }


def document_file_url(request, document: MinibusDocument | None) -> str | None:
    if not document_is_available(document):
        return None
    return request.build_absolute_uri(
        f'/api/v3/minibus/documents/{document.slug}/file',
    )


def resolve_locale(request) -> str:
    query = request.GET.get('locale', '').strip()
    if query:
        return query.split('-')[0].lower()
    island = getattr(request, 'island', None)
    if island and island.default_locale:
        return island.default_locale.split('-')[0].lower()
    return 'pt'


def combine_source_revisions(revisions: list[str]) -> str:
    """Single stable digest for all bundled file revisions (fits source_revision max_length=64)."""
    normalized = ''.join(sorted(set(revisions)))
    if not normalized:
        return ''
    return hashlib.sha256(normalized.encode()).hexdigest()[:32]


def mark_imported(island: Island, *, source_revision: str) -> None:
    meta = get_import_meta(island)
    if meta is None:
        meta = MinibusImportMeta.objects.create(
            island=island,
            source_url=SOURCE_URL,
        )
    meta.source_revision = source_revision
    meta.imported_at = timezone.now()
    meta.save(update_fields=['source_revision', 'imported_at'])
