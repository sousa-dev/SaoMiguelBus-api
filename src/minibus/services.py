"""Mini Bus catalog seeding and API helpers."""

from __future__ import annotations

import hashlib
import heapq
import itertools
import json
import os
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.core.cache import cache
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


def network_stops_path() -> Path:
    return Path(__file__).resolve().parent / 'data' / 'network_stops_sao_miguel.json'


def load_catalog() -> dict[str, Any]:
    with catalog_path().open(encoding='utf-8') as handle:
        return json.load(handle)


def load_network_stops() -> dict[str, Any]:
    with network_stops_path().open(encoding='utf-8') as handle:
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


def serialize_network_stops(*, island: Island, locale: str, request) -> dict[str, Any]:
    """Merge static stop sequences with live line metadata (color, localized name)."""
    network = load_network_stops()
    line_meta = {
        line.code: serialize_line(line, locale=locale, request=request)
        for line in MinibusLine.objects.filter(island=island, is_active=True).order_by('sort_order', 'code')
    }

    lines_payload = []
    for row in network['lines']:
        meta = line_meta.get(row['code'], {})
        lines_payload.append(
            {
                'code': row['code'],
                'slug': row['slug'],
                'name': meta.get('name', row['slug']),
                'color': meta.get('color'),
                'direction': row['direction'],
                'stop_count': row['stop_count'],
                'stops': row['stops'],
            },
        )

    return {
        'source': network.get('source'),
        'extracted_at': network.get('extracted_at'),
        'match_key_notes': network.get('match_key_notes'),
        'interchanges_by_key': network.get('interchanges_by_key', {}),
        'lines': lines_payload,
    }


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


# --- Route search (origin -> destination journey planning) --- #
#
# Schedule-free for now: legs reserve `departure_time`/`arrival_time` (None) so a
# later schedules feature can populate them without changing this contract.

MAX_JOURNEYS = 3


def normalize_token(text: str) -> str:
    """Slugify a stop name/token to compare against match_key/interchange_key."""
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode('ascii').lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')


@dataclass
class StopNode:
    key: str
    line_code: str
    line_slug: str
    sequence: int
    name_pt: str
    match_key: str
    interchange_key: str


@dataclass
class NetworkGraph:
    nodes: dict[str, StopNode] = field(default_factory=dict)
    # adjacency: node key -> list of (neighbour key, is_transfer)
    edges: dict[str, list[tuple[str, bool]]] = field(default_factory=lambda: defaultdict(list))

    def add_edge(self, src: str, dst: str, *, is_transfer: bool) -> None:
        self.edges[src].append((dst, is_transfer))


def build_network_graph(network: dict[str, Any]) -> NetworkGraph:
    """Build a directed stop graph: circular intra-line edges + name-matched transfers."""
    graph = NetworkGraph()

    # Nodes + intra-line edges (sequential, with circular wrap last -> first).
    interchange_groups: dict[str, list[str]] = defaultdict(list)
    for line in network['lines']:
        stops = sorted(line['stops'], key=lambda s: s['sequence'])
        for stop in stops:
            graph.nodes[stop['key']] = StopNode(
                key=stop['key'],
                line_code=line['code'],
                line_slug=line['slug'],
                sequence=stop['sequence'],
                name_pt=stop['name_pt'],
                match_key=stop['match_key'],
                interchange_key=stop['interchange_key'],
            )
            interchange_groups[stop['interchange_key']].append(stop['key'])
        for current, nxt in zip(stops, stops[1:]):
            graph.add_edge(current['key'], nxt['key'], is_transfer=False)
        if len(stops) > 1:
            graph.add_edge(stops[-1]['key'], stops[0]['key'], is_transfer=False)

    # Transfer edges: any two stops sharing an interchange_key but on different lines.
    for keys in interchange_groups.values():
        if len(keys) < 2:
            continue
        for src in keys:
            for dst in keys:
                if src == dst:
                    continue
                if graph.nodes[src].line_code != graph.nodes[dst].line_code:
                    graph.add_edge(src, dst, is_transfer=True)

    return graph


def resolve_stop_refs(graph: NetworkGraph, token: str) -> list[str]:
    """Map a user token (stop key, match_key, interchange_key, or name) to node keys."""
    raw = token.strip().lower()
    slug = normalize_token(token)
    matches: list[str] = []
    for key, node in graph.nodes.items():
        if (
            key == raw
            or node.match_key == slug
            or node.interchange_key == slug
            or normalize_token(node.name_pt) == slug
        ):
            matches.append(key)
    return matches


def _path_to_journey(graph: NetworkGraph, path: tuple[str, ...]) -> dict[str, Any]:
    """Group a node path into per-line legs."""
    legs_nodes: list[list[StopNode]] = []
    current: list[StopNode] = [graph.nodes[path[0]]]
    for key in path[1:]:
        node = graph.nodes[key]
        if node.line_code == current[-1].line_code:
            current.append(node)
        else:
            legs_nodes.append(current)
            current = [node]
    legs_nodes.append(current)

    def stop_ref(node: StopNode) -> dict[str, Any]:
        return {
            'key': node.key,
            'name': node.name_pt,
            'line_code': node.line_code,
            'sequence': node.sequence,
        }

    legs: list[dict[str, Any]] = []
    transfer_stops: list[dict[str, Any]] = []
    for index, nodes in enumerate(legs_nodes):
        legs.append(
            {
                'line_code': nodes[0].line_code,
                'line_slug': nodes[0].line_slug,
                'line_name': None,  # enriched by the view from DB metadata
                'line_color': None,
                'board': stop_ref(nodes[0]),
                'alight': stop_ref(nodes[-1]),
                'stops': [stop_ref(n) for n in nodes],
                'num_stops': len(nodes),
                'departure_time': None,
                'arrival_time': None,
            },
        )
        if index > 0:
            prev_leg = legs_nodes[index - 1]
            transfer_stops.append(
                {
                    'name': prev_leg[-1].name_pt,
                    'from_line': prev_leg[-1].line_code,
                    'to_line': nodes[0].line_code,
                },
            )

    return {
        'transfers': len(legs) - 1,
        'total_stops': sum(leg['num_stops'] for leg in legs),
        'transfer_stops': transfer_stops,
        'legs': legs,
    }


def _leg_signature(journey: dict[str, Any]) -> tuple:
    return tuple((leg['board']['key'], leg['alight']['key']) for leg in journey['legs'])


def search_routes(
    graph: NetworkGraph,
    origin_keys: list[str],
    destination_keys: list[str],
    *,
    max_results: int = MAX_JOURNEYS,
) -> list[dict[str, Any]]:
    """K-shortest journeys minimizing (transfers, total stops) via uniform-cost search."""
    if not origin_keys or not destination_keys:
        return []

    destinations = set(destination_keys)
    counter = itertools.count()
    pq: list[tuple[int, int, int, str, tuple[str, ...]]] = []
    for origin in origin_keys:
        if origin in destinations:
            # Origin already at destination — trivial zero-leg case is meaningless; skip.
            continue
        heapq.heappush(pq, (0, 0, next(counter), origin, (origin,)))

    pop_count: dict[str, int] = defaultdict(int)
    journeys: list[dict[str, Any]] = []
    seen: set[tuple] = set()

    while pq and len(journeys) < max_results:
        transfers, stops, _, node, path = heapq.heappop(pq)
        if pop_count[node] >= max_results:
            continue
        pop_count[node] += 1

        if node in destinations:
            journey = _path_to_journey(graph, path)
            signature = _leg_signature(journey)
            if signature not in seen:
                seen.add(signature)
                journeys.append(journey)
            continue

        for neighbour, is_transfer in graph.edges.get(node, []):
            if neighbour in path:
                continue
            heapq.heappush(
                pq,
                (
                    transfers + (1 if is_transfer else 0),
                    stops + (0 if is_transfer else 1),
                    next(counter),
                    neighbour,
                    path + (neighbour,),
                ),
            )

    return journeys


def enrich_journeys(journeys: list[dict[str, Any]], line_meta: dict[str, dict[str, Any]]) -> None:
    """Fill leg line_name/line_color from per-code DB metadata (mutates in place)."""
    for journey in journeys:
        for leg in journey['legs']:
            meta = line_meta.get(leg['line_code'], {})
            leg['line_name'] = meta.get('name', leg['line_slug'])
            leg['line_color'] = meta.get('color')


def search_minibus_routes(
    *,
    island: Island,
    origin: str,
    destination: str,
    locale: str,
) -> dict[str, Any]:
    """Full route-search payload: resolves tokens, searches, enriches with line metadata."""
    network = load_network_stops()
    graph = build_network_graph(network)
    origin_keys = resolve_stop_refs(graph, origin)
    destination_keys = resolve_stop_refs(graph, destination)
    journeys = search_routes(graph, origin_keys, destination_keys)

    line_meta = {
        line.code: {'name': pick_bilingual_text(pt=line.name_pt, en=line.name_en, locale=locale), 'color': line.color}
        for line in MinibusLine.objects.filter(island=island, is_active=True)
    }
    enrich_journeys(journeys, line_meta)

    def echo(token: str, keys: list[str]) -> dict[str, Any]:
        name = graph.nodes[keys[0]].name_pt if keys else None
        return {'query': token, 'name': name, 'matched': bool(keys)}

    return {
        'origin': echo(origin, origin_keys),
        'destination': echo(destination, destination_keys),
        'journeys': journeys,
    }


# --- Offline bundle (ungated single-snapshot for on-device caching) --- #

BUNDLE_CACHE_TTL = 60 * 60  # 1 hour


def compute_bundle_version(island: Island) -> str:
    """Stable digest of the static datasets + import revision (host-independent)."""
    digest = hashlib.sha256()
    digest.update(catalog_path().read_bytes())
    digest.update(network_stops_path().read_bytes())
    meta = get_import_meta(island)
    digest.update((meta.source_revision if meta else '').encode())
    return digest.hexdigest()[:16]


def build_offline_bundle(*, island: Island, locale: str, request) -> dict[str, Any]:
    """Everything the app caches for offline Mini Bus: lines, tariffs, network, images."""
    host = request.get_host()
    cache_key = f'minibus:offline:v2:{island.key}:{locale}:{host}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    lines = [
        serialize_line(line, locale=locale, request=request)
        for line in MinibusLine.objects.filter(island=island, is_active=True).order_by('sort_order', 'code')
    ]
    tariffs = [
        serialize_tariff(tariff, locale=locale)
        for tariff in MinibusTariff.objects.filter(island=island, is_active=True).order_by('sort_order', 'key')
    ]
    network = serialize_network_stops(island=island, locale=locale, request=request)
    images = [
        {
            'line_code': line['code'],
            'line_slug': line['slug'],
            'slug': line['timetable_slug'],
            'url': line['timetable_file_url'],
        }
        for line in lines
        if line.get('timetable_file_url')
    ]

    network_map_doc = MinibusDocument.objects.filter(
        island=island,
        slug='network-map',
        doc_type=MinibusDocument.DOC_NETWORK_MAP,
        is_active=True,
    ).first()
    network_map = None
    if document_is_available(network_map_doc):
        network_map = {
            'slug': network_map_doc.slug,
            'url': document_file_url(request, network_map_doc),
        }

    payload = {
        'version': compute_bundle_version(island),
        'generated_at': timezone.now().isoformat(),
        'lines': lines,
        'tariffs': tariffs,
        'network': network,
        'images': images,
        'network_map': network_map,
        **build_meta_payload(island),
    }
    cache.set(cache_key, payload, BUNDLE_CACHE_TTL)
    return payload
