"""Trails and POI sync from dados.gov.pt open data."""

from __future__ import annotations

import logging
import math
import os
from typing import Any

import requests
from django.conf import settings

from tenancy.models import Island
from tenancy.services import for_island
from trails.models import POI, Trail

logger = logging.getLogger(__name__)

UDATA_API_BASE = 'https://dados.gov.pt/api/1'
# Percursos Pedestres (PP) Homologados — WFS/ArcGIS MapServer (dados.gov.pt udata id)
DEFAULT_TRAILS_DATASET_ID = '653b2113b318b3ef7b1529cc'
# Pontos de Interesse Turístico (PIT) — WMS (POI sync best-effort when vector unavailable)
DEFAULT_POI_DATASET_ID = '653b211336fa4dbc2b1529cb'
REQUEST_TIMEOUT_SECONDS = 60
KM_PER_DEGREE_LAT = 111.0
OPEN_DATA_ATTRIBUTION = (
    'Dados abertos — Região Autónoma dos Açores via dados.gov.pt (CC BY 4.0).'
)

LINE_GEOMETRIES = frozenset({'LineString', 'MultiLineString'})
POINT_GEOMETRIES = frozenset({'Point'})


def _trails_dataset_id() -> str:
    return (
        getattr(settings, 'DADOS_GOV_TRAILS_DATASET_ID', None)
        or os.environ.get('DADOS_GOV_TRAILS_DATASET_ID')
        or getattr(settings, 'DADOS_GOV_TRAILS_PACKAGE', None)
        or os.environ.get('DADOS_GOV_TRAILS_PACKAGE')
        or DEFAULT_TRAILS_DATASET_ID
    )


def _poi_dataset_id() -> str:
    return (
        getattr(settings, 'DADOS_GOV_POI_DATASET_ID', None)
        or os.environ.get('DADOS_GOV_POI_DATASET_ID')
        or getattr(settings, 'DADOS_GOV_POI_PACKAGE', None)
        or os.environ.get('DADOS_GOV_POI_PACKAGE')
        or DEFAULT_POI_DATASET_ID
    )


def _km_to_degrees(km: float) -> float:
    return max(km / KM_PER_DEGREE_LAT, 0.01)


def island_bbox(island: Island) -> tuple[float, float, float, float]:
    """Return (min_lat, max_lat, min_lng, max_lng) for island center + radius."""
    delta = _km_to_degrees(float(island.radius_km))
    lng_delta = delta / max(math.cos(math.radians(island.center_lat)), 0.1)
    return (
        island.center_lat - delta,
        island.center_lat + delta,
        island.center_lng - lng_delta,
        island.center_lng + lng_delta,
    )


def _coord_in_bbox(lat: float, lng: float, bbox: tuple[float, float, float, float]) -> bool:
    min_lat, max_lat, min_lng, max_lng = bbox
    return min_lat <= lat <= max_lat and min_lng <= lng <= max_lng


def _iter_coordinates(geometry: dict[str, Any]) -> list[tuple[float, float]]:
    geom_type = geometry.get('type') or ''
    coords = geometry.get('coordinates')
    if not coords:
        return []

    if geom_type == 'Point':
        return [(float(coords[1]), float(coords[0]))]

    if geom_type == 'LineString':
        return [(float(c[1]), float(c[0])) for c in coords if isinstance(c, (list, tuple)) and len(c) >= 2]

    if geom_type == 'MultiLineString':
        points: list[tuple[float, float]] = []
        for line in coords:
            if not isinstance(line, (list, tuple)):
                continue
            for c in line:
                if isinstance(c, (list, tuple)) and len(c) >= 2:
                    points.append((float(c[1]), float(c[0])))
        return points

    points: list[tuple[float, float]] = []

    def walk(node: Any) -> None:
        if isinstance(node, (list, tuple)):
            if (
                len(node) >= 2
                and isinstance(node[0], (int, float))
                and isinstance(node[1], (int, float))
                and (len(node) == 2 or not isinstance(node[2], (list, tuple)))
            ):
                points.append((float(node[1]), float(node[0])))
                return
            for item in node:
                walk(item)

    walk(coords)
    return points


def feature_in_island(feature: dict[str, Any], island: Island) -> bool:
    geometry = feature.get('geometry') or {}
    points = _iter_coordinates(geometry)
    if not points:
        return False
    bbox = island_bbox(island)
    return any(_coord_in_bbox(lat, lng, bbox) for lat, lng in points)


def _first_property(props: dict[str, Any], *keys: str) -> str:
    for key in keys:
        for candidate in (key, key.upper(), key.lower(), key.capitalize()):
            value = props.get(candidate)
            if value is not None and str(value).strip():
                return str(value).strip()
    return ''


def _extract_source_ref(feature: dict[str, Any]) -> str:
    props = feature.get('properties') or {}
    ref = _first_property(
        props,
        'id',
        'OBJECTID',
        'objectid',
        'codigo',
        'CODIGO',
        'Id',
        'ID',
        'fid',
        'FID',
    )
    if ref:
        return ref[:128]
    feature_id = feature.get('id')
    if feature_id is not None and str(feature_id).strip():
        return str(feature_id).strip()[:128]
    return ''


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _line_length_km(geometry: dict[str, Any]) -> float | None:
    points = _iter_coordinates(geometry)
    if len(points) < 2:
        return None
    total = 0.0
    for i in range(1, len(points)):
        lat1, lng1 = points[i - 1]
        lat2, lng2 = points[i]
        total += _haversine_km(lat1, lng1, lat2, lng2)
    return round(total, 2) if total > 0 else None


def _normalize_difficulty(raw: str) -> str:
    value = raw.strip().lower()
    if not value:
        return ''
    if value in {'easy', 'facil', 'fácil', 'baixo', 'low', '1'}:
        return 'easy'
    if value in {'moderate', 'medio', 'médio', 'medium', 'moderado', '2'}:
        return 'moderate'
    if value in {'hard', 'dificil', 'difícil', 'alto', 'high', '3'}:
        return 'hard'
    return raw.strip()[:32]


def parse_trail_feature(feature: dict[str, Any]) -> dict[str, Any] | None:
    geometry = feature.get('geometry') or {}
    geom_type = geometry.get('type') or ''
    if geom_type not in LINE_GEOMETRIES:
        return None

    source_ref = _extract_source_ref(feature)
    if not source_ref:
        return None

    props = feature.get('properties') or {}
    name = _first_property(
        props,
        'nome',
        'name',
        'designacao',
        'Designacao',
        'NOME',
        'titulo',
        'nome_percurso',
        'NOME_PERCURSO',
    )
    if not name:
        name = f'Trail {source_ref}'

    difficulty_raw = _first_property(
        props,
        'dificuldade',
        'difficulty',
        'grau_dificuldade',
        'grau',
        'DIFICULDADE',
    )
    difficulty = _normalize_difficulty(difficulty_raw)

    distance_raw = _first_property(
        props,
        'distancia',
        'distance',
        'comprimento',
        'length_km',
        'DISTANCIA',
        'extensao',
    )
    distance_km: float | None = None
    if distance_raw:
        try:
            distance_km = float(str(distance_raw).replace(',', '.').split()[0])
        except ValueError:
            distance_km = None
    if distance_km is None:
        distance_km = _line_length_km(geometry)

    return {
        'source_ref': source_ref,
        'name': name[:200],
        'difficulty': difficulty,
        'distance_km': distance_km,
        'geojson': geometry,
    }


def parse_poi_feature(feature: dict[str, Any]) -> dict[str, Any] | None:
    geometry = feature.get('geometry') or {}
    geom_type = geometry.get('type') or ''
    if geom_type not in POINT_GEOMETRIES:
        return None

    source_ref = _extract_source_ref(feature)
    if not source_ref:
        return None

    props = feature.get('properties') or {}
    name = _first_property(props, 'nome', 'name', 'designacao', 'Designacao', 'NOME', 'titulo')
    if not name:
        name = f'POI {source_ref}'

    category = _first_property(
        props,
        'categoria',
        'category',
        'tipo',
        'type',
        'TIPO',
        'CATEGORIA',
        'classificacao',
    )[:64]

    coords = geometry.get('coordinates') or []
    if len(coords) < 2:
        return None

    return {
        'source_ref': source_ref,
        'name': name[:200],
        'category': category,
        'latitude': float(coords[1]),
        'longitude': float(coords[0]),
    }


def _normalize_feature_collection(data: dict[str, Any]) -> dict[str, Any]:
    if data.get('type') == 'Feature':
        return {'type': 'FeatureCollection', 'features': [data]}
    features = data.get('features')
    if isinstance(features, list):
        return {'type': 'FeatureCollection', 'features': features}
    raise ValueError('Response is not a GeoJSON FeatureCollection')


def _merge_feature_collections(collections: list[dict[str, Any]]) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    for collection in collections:
        for feature in collection.get('features') or []:
            if isinstance(feature, dict):
                features.append(feature)
    return {'type': 'FeatureCollection', 'features': features}


def fetch_udata_dataset(dataset_id: str) -> dict[str, Any]:
    response = requests.get(
        f'{UDATA_API_BASE}/datasets/{dataset_id}/',
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f'Invalid dataset payload for {dataset_id}')
    return payload


def _arcgis_mapserver_geojson(resource_url: str, *, layer_id: int = 0) -> dict[str, Any]:
    base = resource_url.split('?')[0]
    for suffix in ('/WFSServer', '/WFS'):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    if not base.endswith('/MapServer'):
        if '/MapServer/' in base:
            base = base.split('/MapServer/')[0] + '/MapServer'
    query_url = f'{base}/{layer_id}/query'
    response = requests.get(
        query_url,
        params={
            'where': '1=1',
            'outFields': '*',
            'f': 'geojson',
            'returnGeometry': 'true',
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return _normalize_feature_collection(response.json())


def _download_geojson_url(url: str) -> dict[str, Any]:
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return _normalize_feature_collection(response.json())


def fetch_resource_geojson(resource: dict[str, Any]) -> dict[str, Any]:
    fmt = str(resource.get('format') or '').upper()
    url = str(resource.get('url') or '').strip()
    if not url:
        raise ValueError('Resource missing URL')

    if fmt in {'GEOJSON', 'JSON'} or url.lower().endswith(('.geojson', '.json')):
        return _download_geojson_url(url)

    if fmt == 'WFS' or 'WFSServer' in url or '/WFS' in url.upper():
        return _arcgis_mapserver_geojson(url)

    if fmt == 'WMS':
        raise ValueError(f'WMS-only resource has no vector download: {url[:80]}')

    raise ValueError(f'Unsupported resource format: {fmt or "unknown"}')


def fetch_dataset_geojson(dataset_id: str) -> dict[str, Any]:
    """Resolve dados.gov.pt udata dataset and return merged FeatureCollection."""
    dataset = fetch_udata_dataset(dataset_id)
    resources = dataset.get('resources') or []
    if not isinstance(resources, list) or not resources:
        raise ValueError(f'Dataset {dataset_id} has no resources')

    collections: list[dict[str, Any]] = []
    errors: list[str] = []
    for resource in resources:
        if not isinstance(resource, dict):
            continue
        try:
            collections.append(fetch_resource_geojson(resource))
        except Exception as exc:
            errors.append(str(exc))
            logger.warning(
                'trails resource fetch skipped dataset=%s resource=%s: %s',
                dataset_id,
                resource.get('id'),
                exc,
            )

    if not collections:
        detail = '; '.join(errors[:3]) if errors else 'no vector resources'
        raise ValueError(f'No fetchable GeoJSON for dataset {dataset_id}: {detail}')

    return _merge_feature_collections(collections)


def fetch_package_geojson(dataset_id: str) -> dict[str, Any]:
    """Backward-compatible alias for dataset GeoJSON fetch."""
    return fetch_dataset_geojson(dataset_id)


def sync_trails_for_island(island: Island, *, collection: dict[str, Any] | None = None) -> dict[str, int]:
    counts = {'created': 0, 'updated': 0, 'skipped': 0}
    if collection is None:
        collection = fetch_dataset_geojson(_trails_dataset_id())

    features = collection.get('features') or []
    with for_island(island):
        for feature in features:
            if not isinstance(feature, dict):
                counts['skipped'] += 1
                continue
            if not feature_in_island(feature, island):
                counts['skipped'] += 1
                continue
            row = parse_trail_feature(feature)
            if not row:
                counts['skipped'] += 1
                continue
            _, created = Trail.objects.update_or_create(
                island=island,
                source_ref=row['source_ref'],
                defaults={
                    'name': row['name'],
                    'difficulty': row['difficulty'],
                    'distance_km': row['distance_km'],
                    'geojson': row['geojson'],
                },
            )
            if created:
                counts['created'] += 1
            else:
                counts['updated'] += 1
    return counts


def sync_pois_for_island(island: Island, *, collection: dict[str, Any] | None = None) -> dict[str, int]:
    counts = {'created': 0, 'updated': 0, 'skipped': 0}
    if collection is None:
        collection = fetch_dataset_geojson(_poi_dataset_id())

    features = collection.get('features') or []
    with for_island(island):
        for feature in features:
            if not isinstance(feature, dict):
                counts['skipped'] += 1
                continue
            if not feature_in_island(feature, island):
                counts['skipped'] += 1
                continue
            row = parse_poi_feature(feature)
            if not row:
                counts['skipped'] += 1
                continue
            _, created = POI.objects.update_or_create(
                island=island,
                source_ref=row['source_ref'],
                defaults={
                    'name': row['name'],
                    'category': row['category'],
                    'latitude': row['latitude'],
                    'longitude': row['longitude'],
                },
            )
            if created:
                counts['created'] += 1
            else:
                counts['updated'] += 1
    return counts


def _islands_for_sync(*, island_key: str | None) -> list[Island]:
    if island_key:
        return list(Island.objects.filter(key=island_key))
    return [
        island
        for island in Island.objects.all()
        if (island.feature_flags or {}).get('trails')
    ]


def sync_open_data_for_island(island: Island) -> dict[str, int]:
    totals = {
        'trails_created': 0,
        'trails_updated': 0,
        'pois_created': 0,
        'pois_updated': 0,
        'skipped': 0,
    }
    try:
        from trails.visitazores_sync import sync_visitazores_trails_for_island

        trail_counts = sync_visitazores_trails_for_island(island)
        totals['trails_created'] += trail_counts['created']
        totals['trails_updated'] += trail_counts['updated']
        totals['skipped'] += trail_counts['skipped']
    except Exception:
        logger.exception('visitazores trails sync failed for island=%s', island.key)
        raise

    try:
        poi_collection = fetch_dataset_geojson(_poi_dataset_id())
        poi_counts = sync_pois_for_island(island, collection=poi_collection)
        totals['pois_created'] += poi_counts['created']
        totals['pois_updated'] += poi_counts['updated']
        totals['skipped'] += poi_counts['skipped']
    except Exception:
        logger.exception('poi sync skipped for island=%s (best-effort)', island.key)

    return totals


def propagate_trails_to_atlas(islands: list[Island]) -> int:
    """Push freshly-synced trails into AtlasTrail so offline clients actually see them.

    Trails otherwise reach atlas only via atlas.import_all_sources, which is beat-scheduled
    monthly (1st, 02:00 Azores) — so a nightly trails sync stayed invisible to the offline map
    app for up to a month, and a deploy-time sync until the following month.

    Best-effort and DB-only (no network, no Overpass, no Visit Azores): the trails sync has
    already succeeded by this point and must not be failed by a problem downstream of it.
    Skips islands without the atlas flag, since they have no AtlasRevision to hang rows off.
    """
    from atlas.importers.trails import TrailsImporter

    imported = 0
    for island in islands:
        if not (island.feature_flags or {}).get('atlas'):
            continue
        try:
            TrailsImporter(island).run()
        except Exception:
            logger.exception('atlas trails import failed for island=%s', island.key)
            continue
        imported += 1
    return imported


def sync_all_open_data(*, island_key: str | None = None) -> dict[str, int]:
    """Sync every flagged island (or one). One island's failure never aborts the others.

    sync_open_data_for_island() re-raises on a trails failure so a targeted single-island run
    still surfaces the error to its caller. Across nine islands that would mean one flaky
    listing fetch loses the whole nightly run, so failures are contained and counted here.

    Successfully synced islands are then propagated into atlas — see
    propagate_trails_to_atlas() for why that is part of finishing a sync rather than a
    separate monthly job.
    """
    totals = {
        'islands': 0,
        'trails_created': 0,
        'trails_updated': 0,
        'pois_created': 0,
        'pois_updated': 0,
        'skipped': 0,
        'failed_islands': 0,
        'atlas_islands_imported': 0,
    }
    synced: list[Island] = []
    for island in _islands_for_sync(island_key=island_key):
        totals['islands'] += 1
        try:
            counts = sync_open_data_for_island(island)
        except Exception:
            logger.exception('open data sync failed for island=%s — continuing', island.key)
            totals['failed_islands'] += 1
            continue
        synced.append(island)
        for key in ('trails_created', 'trails_updated', 'pois_created', 'pois_updated', 'skipped'):
            totals[key] += counts[key]

    totals['atlas_islands_imported'] = propagate_trails_to_atlas(synced)
    return totals


def nearest_stop(island: Island, lat: float | None, lng: float | None) -> dict[str, Any] | None:
    if lat is None or lng is None:
        return None

    from transit.models import Stop
    from transit.services.schedule_phase import resolve_dataset

    best: Stop | None = None
    best_dist = float('inf')
    dataset = resolve_dataset(island)
    for stop in Stop.objects.filter(island=island, dataset=dataset):
        dist = _haversine_km(lat, lng, stop.latitude, stop.longitude)
        if dist < best_dist:
            best_dist = dist
            best = stop

    if best is None:
        return None

    return {
        'name': best.name,
        'distanceKm': round(best_dist, 2),
        'lat': best.latitude,
        'lng': best.longitude,
    }


def serialize_trail_summary(trail: Trail) -> dict[str, Any]:
    return {
        'id': trail.id,
        'sourceRef': trail.source_ref,
        'name': trail.name,
        'difficulty': trail.difficulty,
        'distanceKm': trail.distance_km,
        'shape': trail.shape,
        'durationMin': trail.duration_min,
        'mapImageUrl': trail.map_image_url,
    }


def serialize_trail_detail(trail: Trail) -> dict[str, Any]:
    stages = [
        {
            'id': stage.id,
            'name': stage.name,
            'sequence': stage.sequence,
            'geojson': stage.geojson,
        }
        for stage in trail.stages.order_by('sequence')
    ]
    nearest = nearest_stop(trail.island, trail.start_lat, trail.start_lon)
    return {
        **serialize_trail_summary(trail),
        'descriptionPt': trail.description_pt,
        'descriptionEn': trail.description_en,
        'gpxUrl': trail.gpx_url,
        'kmlUrl': trail.kml_url,
        'mapImageUrl': trail.map_image_url,
        'leafletUrl': trail.leaflet_url,
        'startLat': trail.start_lat,
        'startLng': trail.start_lon,
        'waypoints': trail.waypoints or [],
        'nearestStop': nearest,
        'geojson': trail.geojson,
        'stages': stages,
        'attribution': trails_attribution(),
    }


def serialize_poi(poi: POI) -> dict[str, Any]:
    return {
        'id': poi.id,
        'name': poi.name,
        'category': poi.category,
        'latitude': poi.latitude,
        'longitude': poi.longitude,
    }


def trails_attribution() -> str:
    try:
        from trails.visitazores_sync import VISITAZORES_ATTRIBUTION

        return VISITAZORES_ATTRIBUTION
    except ImportError:
        return OPEN_DATA_ATTRIBUTION


def list_trails(
    *,
    difficulty: str = '',
    shape: str = '',
    min_length: float | None = None,
    max_length: float | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    qs = Trail.objects.order_by('name')
    if difficulty:
        qs = qs.filter(difficulty__iexact=difficulty.strip())
    if shape:
        qs = qs.filter(shape__iexact=shape.strip())
    if min_length is not None:
        qs = qs.filter(distance_km__gte=min_length)
    if max_length is not None:
        qs = qs.filter(distance_km__lte=max_length)
    limit = max(1, min(limit, 100))
    return {
        'trails': [serialize_trail_summary(trail) for trail in qs[:limit]],
        'attribution': trails_attribution(),
    }


def get_trail(trail_id: int) -> dict[str, Any] | None:
    try:
        trail = Trail.objects.prefetch_related('stages').get(id=trail_id)
    except Trail.DoesNotExist:
        return None
    return serialize_trail_detail(trail)


def list_pois(*, category: str = '', limit: int = 50) -> dict[str, Any]:
    qs = POI.objects.order_by('name')
    if category:
        qs = qs.filter(category__icontains=category.strip())
    limit = max(1, min(limit, 100))
    return {
        'pois': [serialize_poi(poi) for poi in qs[:limit]],
        'attribution': trails_attribution(),
    }
