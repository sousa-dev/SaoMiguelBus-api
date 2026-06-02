"""Transit business logic and legacy ETL."""

from __future__ import annotations

import ast
import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, time
from pathlib import Path
from typing import Any, Callable, Iterator, Union
from urllib.parse import urlparse

from django.db import connection, models, transaction
from django.utils.dateparse import parse_date, parse_datetime
from django.utils import timezone

from tenancy.models import Island
from tenancy.services import for_island
from transit.models import (
    Ad,
    Calendar,
    Holiday,
    Line,
    Operator,
    RouteInfo,
    Stop,
    StopGroup,
    StopTime,
    Trip,
)

logger = logging.getLogger(__name__)

LEGACY_DAY_MAP = {
    'WEEKDAY': Calendar.WEEKDAY,
    'SATURDAY': Calendar.SATURDAY,
    'SUNDAY': Calendar.SUNDAY,
    'weekday': Calendar.WEEKDAY,
    'saturday': Calendar.SATURDAY,
    'sunday': Calendar.SUNDAY,
}

OPERATOR_PREFIXES = (
    ('CRP', 'CRP'),
    ('AVM', 'AVM'),
    ('Varela', 'Varela'),
)

LEGACY_EXPORT_FORMAT_VERSION = 2
SUPPORTED_EXPORT_FORMAT_VERSIONS = {1, 2}

FULL_IMPORT_ORDER = [
    'islands',
    'operators',
    'stops',
    'stop_groups',
    'calendars',
    'holidays',
    'lines_trips',
    'infos',
    'ads',
    'subscriptions',
    'stats',
    'data',
    'legacy_trips',
    'legacy_tripstops',
    'aifeedback',
    'emailopens',
]

# Safe to skip when export omitted optional archive tables (e.g. no app_data).
OPTIONAL_IMPORT_STEPS = frozenset({
    'data',
    'legacy_trips',
    'legacy_tripstops',
    'aifeedback',
    'emailopens',
})

BULK_IMPORT_BATCH_SIZE = 5000

# Tables in legacy export JSON (matches pull_legacy_export / main-temp batch order).
LEGACY_EXPORT_TABLE_ORDER = [
    'app_variables',
    'app_stop',
    'app_holiday',
    'app_group',
    'app_route',
    'app_ad',
    'app_info',
    'subscriptions',
    'app_stat',
    'app_data',
    'app_trip',
    'app_tripstop',
    'app_aifeedback',
    'app_emailopen',
]

BATCHED_EXPORT_LAYOUT = 'batched_jsonl'

QUERY_VARIABLES = (
    'SELECT id, version, maps, populate_maps_routes FROM app_variables ORDER BY id'
)
QUERY_STOPS = (
    'SELECT id, name, cleaned_name, latitude, longitude FROM app_stop ORDER BY id'
)
QUERY_HOLIDAYS = 'SELECT id, date, name FROM app_holiday ORDER BY date'
QUERY_GROUPS = 'SELECT id, name, stops FROM app_group ORDER BY id'
QUERY_ROUTES = (
    'SELECT id, route, stops, type_of_day, information, disabled, likes, dislikes '
    'FROM app_route ORDER BY id'
)
QUERY_ADS = (
    'SELECT id, entity, description, media, start, end, action, target, '
    'advertise_on, platform, status, seen, clicked FROM app_ad ORDER BY id'
)
QUERY_INFOS = (
    'SELECT id, titlePT, messagePT, titleEN, messageEN, titleES, messageES, '
    'titleFR, messageFR, titleDE, messageDE, start, end, source, company '
    'FROM app_info ORDER BY id'
)
QUERY_SUBSCRIPTIONS = (
    'SELECT id, email, is_active, verification_count, created_at, updated_at '
    'FROM subscriptions ORDER BY id'
)
QUERY_STATS = (
    'SELECT id, request, origin, destination, type_of_day, time, platform, language, timestamp '
    'FROM app_stat ORDER BY id'
)
QUERY_DATA = (
    'SELECT id, data, origin, destination, language_code, time, platform '
    'FROM app_data ORDER BY id'
)
QUERY_TRIPS = (
    'SELECT id, route, stops, cleaned_stops, type_of_day, information, disabled, added, likes, dislikes '
    'FROM app_trip ORDER BY id'
)
QUERY_TRIPSTOPS = (
    'SELECT id, name, latitude, longitude, cleaned_name FROM app_tripstop ORDER BY id'
)
QUERY_AIFEEDBACK = (
    'SELECT id, language, first_time, residence_status, guide_preference, payment_willingness, timestamp '
    'FROM app_aifeedback ORDER BY id'
)
QUERY_EMAILOPENS = (
    'SELECT id, email_template_id, contact_id, clicks FROM app_emailopen ORDER BY id'
)

TABLE_COLUMNS: dict[str, list[str]] = {
    'app_variables': ['id', 'version', 'maps', 'populate_maps_routes'],
    'app_stop': ['id', 'name', 'cleaned_name', 'latitude', 'longitude'],
    'app_holiday': ['id', 'date', 'name'],
    'app_group': ['id', 'name', 'stops'],
    'app_route': [
        'id', 'route', 'stops', 'type_of_day', 'information', 'disabled', 'likes', 'dislikes',
    ],
    'app_ad': [
        'id', 'entity', 'description', 'media', 'start', 'end', 'action', 'target',
        'advertise_on', 'platform', 'status', 'seen', 'clicked',
    ],
    'app_info': [
        'id', 'titlePT', 'messagePT', 'titleEN', 'messageEN', 'titleES', 'messageES',
        'titleFR', 'messageFR', 'titleDE', 'messageDE', 'start', 'end', 'source', 'company',
    ],
    'subscriptions': [
        'id', 'email', 'is_active', 'verification_count', 'created_at', 'updated_at',
    ],
    'app_stat': [
        'id', 'request', 'origin', 'destination', 'type_of_day', 'time', 'platform', 'language', 'timestamp',
    ],
    'app_data': ['id', 'data', 'origin', 'destination', 'language_code', 'time', 'platform'],
    'app_trip': [
        'id', 'route', 'stops', 'cleaned_stops', 'type_of_day', 'information',
        'disabled', 'added', 'likes', 'dislikes',
    ],
    'app_tripstop': ['id', 'name', 'latitude', 'longitude', 'cleaned_name'],
    'app_aifeedback': [
        'id', 'language', 'first_time', 'residence_status', 'guide_preference',
        'payment_willingness', 'timestamp',
    ],
    'app_emailopen': ['id', 'email_template_id', 'contact_id', 'clicks'],
}

TABLE_SQL = {
    'app_variables': QUERY_VARIABLES,
    'app_stop': QUERY_STOPS,
    'app_holiday': QUERY_HOLIDAYS,
    'app_group': QUERY_GROUPS,
    'app_route': QUERY_ROUTES,
    'app_ad': QUERY_ADS,
    'app_info': QUERY_INFOS,
    'subscriptions': QUERY_SUBSCRIPTIONS,
    'app_stat': QUERY_STATS,
    'app_data': QUERY_DATA,
    'app_trip': QUERY_TRIPS,
    'app_tripstop': QUERY_TRIPSTOPS,
    'app_aifeedback': QUERY_AIFEEDBACK,
    'app_emailopen': QUERY_EMAILOPENS,
}

def _normalize_sql(sql: str) -> str:
    return ' '.join(sql.split())


LEGACY_SQL_TABLE_MAP = {_normalize_sql(sql): table for table, sql in TABLE_SQL.items()}

_LEGACY_DATE_FIELDS: dict[str, set[str]] = {
    'app_holiday': {'date'},
}
_LEGACY_DATETIME_FIELDS: dict[str, set[str]] = {
    'app_ad': {'start', 'end'},
    'app_info': {'start', 'end'},
    'app_stat': {'timestamp'},
    'app_trip': {'added'},
    'app_aifeedback': {'timestamp'},
    'subscriptions': {'created_at', 'updated_at'},
}

LegacySource = Union['LegacyDatabase', 'LegacyExportSource', 'LegacyBatchedExportSource']


@dataclass
class MigrationReport:
    step: str
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            'step': self.step,
            'created': self.created,
            'updated': self.updated,
            'skipped': self.skipped,
            'errors': self.errors,
        }


def clean_string(value: str) -> str:
    """Match legacy stop name normalization."""
    translation_table = str.maketrans(
        'áàâãäéèêëíìîïóòôõöúùûüç',
        'aaaaaeeeeiiiiooooouuuuc',
    )
    return ' '.join(value.lower().translate(translation_table).replace('-', '').split())


def parse_legacy_stops(raw: Any) -> dict | None:
    """Parse legacy Route.stops (JSON-wrapped Python dict string)."""
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return None
    try:
        inner = json.loads(raw)
    except json.JSONDecodeError:
        inner = raw
    if isinstance(inner, dict):
        return inner
    if isinstance(inner, str):
        try:
            parsed = ast.literal_eval(inner)
            return parsed if isinstance(parsed, dict) else None
        except (SyntaxError, ValueError):
            return None
    return None


def parse_legacy_time(raw: str) -> time | None:
    """Convert legacy '08h30' or '08:30' strings to time."""
    if not raw:
        return None
    normalized = raw.strip().lower().replace('h', ':')
    match = re.match(r'^(\d{1,2}):(\d{2})$', normalized)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)


def infer_operator_name(route_code: str) -> str:
    code = (route_code or '').strip()
    for prefix, name in OPERATOR_PREFIXES:
        if code.upper().startswith(prefix):
            return name
    return 'Other'


class LegacyDatabase:
    """Read-only access to legacy SQLite or Postgres via Django secondary DB."""

    def __init__(self, legacy_db_url: str | None = None):
        self.legacy_db_url = legacy_db_url
        self._sqlite_path: Path | None = None
        if legacy_db_url and legacy_db_url.startswith('sqlite:'):
            raw = legacy_db_url.replace('sqlite:///', '', 1)
            path = Path(raw)
            if not path.is_absolute():
                path = (Path.cwd() / path).resolve()
            self._sqlite_path = path

    def fetchall(self, sql: str, params: tuple = ()) -> list[tuple]:
        if self._sqlite_path:
            conn = sqlite3.connect(self._sqlite_path)
            try:
                return conn.execute(sql, params).fetchall()
            finally:
                conn.close()
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()

    def get_records(self, table: str) -> list[dict[str, Any]]:
        sql = TABLE_SQL[table]
        columns = TABLE_COLUMNS[table]
        return [
            dict(zip(columns, row, strict=True))
            for row in self.fetchall(sql)
        ]

    def iter_records(self, table: str) -> Iterator[dict[str, Any]]:
        yield from self.get_records(table)


def _coerce_record_dict(table: str, record: dict[str, Any]) -> dict[str, Any]:
    coerced = dict(record)
    for field in _LEGACY_DATE_FIELDS.get(table, set()):
        value = coerced.get(field)
        if isinstance(value, str):
            coerced[field] = parse_date(value[:10]) or value
    for field in _LEGACY_DATETIME_FIELDS.get(table, set()):
        value = coerced.get(field)
        if isinstance(value, str):
            coerced[field] = parse_datetime(value) or value
    return coerced


def _coerce_export_cell(table: str, index: int, value: Any) -> Any:
    if value is None or not isinstance(value, str):
        return value
    columns = TABLE_COLUMNS.get(table, [])
    if index >= len(columns):
        return value
    field = columns[index]
    if field in _LEGACY_DATE_FIELDS.get(table, set()):
        parsed = parse_date(value[:10])
        return parsed or value
    if field in _LEGACY_DATETIME_FIELDS.get(table, set()):
        parsed = parse_datetime(value)
        return parsed or value
    return value


def _coerce_export_row(table: str, row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return _coerce_record_dict(table, row)
    columns = TABLE_COLUMNS[table]
    return _coerce_record_dict(
        table,
        dict(
            zip(
                columns,
                (
                    _coerce_export_cell(table, index, value)
                    for index, value in enumerate(row)
                ),
                strict=True,
            )
        ),
    )


class LegacyBatchedExportSource:
    """Stream rows from a split export directory (manifest.json + JSONL batch files)."""

    def __init__(self, export_dir: str | Path):
        self.export_dir = Path(export_dir).resolve()
        manifest_path = self.export_dir / 'manifest.json'
        if not manifest_path.is_file():
            raise FileNotFoundError(
                f'Batched export manifest not found: {manifest_path}'
            )
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        version = manifest.get('format_version')
        if version not in SUPPORTED_EXPORT_FORMAT_VERSIONS:
            raise ValueError(
                f'Unsupported export format_version={version!r} '
                f'(expected one of {sorted(SUPPORTED_EXPORT_FORMAT_VERSIONS)})'
            )
        if manifest.get('layout') != BATCHED_EXPORT_LAYOUT:
            raise ValueError(
                f'Unsupported batched export layout={manifest.get("layout")!r} '
                f'(expected {BATCHED_EXPORT_LAYOUT!r})'
            )
        self.format_version = version
        self.exported_at = manifest.get('exported_at')
        self.source = manifest.get('source')
        self.table_counts: dict[str, int] = dict(manifest.get('table_counts') or {})
        self._batches: list[dict[str, Any]] = sorted(
            manifest.get('batches') or [],
            key=lambda item: int(item.get('seq', 0)),
        )
        batches_by_table: dict[str, list[dict[str, Any]]] = {}
        for batch in self._batches:
            batches_by_table.setdefault(batch['table'], []).append(batch)
        self._batches_by_table = batches_by_table

    def _iter_jsonl_rows(self, relative_file: str) -> Iterator[Any]:
        path = self.export_dir / relative_file
        if not path.is_file():
            raise FileNotFoundError(f'Export batch file not found: {path}')
        with path.open('r', encoding='utf-8') as handle:
            for line in handle:
                stripped = line.strip()
                if stripped:
                    yield json.loads(stripped)

    def iter_records(self, table: str) -> Iterator[dict[str, Any]]:
        for batch in self._batches_by_table.get(table, []):
            for row in self._iter_jsonl_rows(batch['file']):
                yield _coerce_export_row(table, row)

    def get_records(self, table: str) -> list[dict[str, Any]]:
        return list(self.iter_records(table))

    def fetchall(self, sql: str, params: tuple = ()) -> list[tuple]:
        if params:
            raise NotImplementedError('Parameterized legacy export queries are not supported')
        table = LEGACY_SQL_TABLE_MAP.get(_normalize_sql(sql))
        if table is None:
            raise ValueError(f'Unsupported legacy export query: {sql}')
        columns = TABLE_COLUMNS[table]
        return [
            tuple(record.get(column) for column in columns)
            for record in self.iter_records(table)
        ]


class LegacyExportSource:
    """Read legacy rows from JSON produced by GET /api/v1/export/legacy."""

    def __init__(self, export_path: str | Path):
        path = Path(export_path)
        if not path.is_file():
            raise FileNotFoundError(f'Legacy export file not found: {path}')
        payload = json.loads(path.read_text(encoding='utf-8'))
        version = payload.get('format_version')
        if version not in SUPPORTED_EXPORT_FORMAT_VERSIONS:
            raise ValueError(
                f'Unsupported export format_version={version!r} '
                f'(expected one of {sorted(SUPPORTED_EXPORT_FORMAT_VERSIONS)})'
            )
        self.export_path = path
        self.format_version = version
        self.exported_at = payload.get('exported_at')
        self.source = payload.get('source')
        self.tables: dict[str, Any] = payload.get('tables', {})

    def table_counts(self) -> dict[str, int]:
        return {name: len(rows) for name, rows in self.tables.items() if rows}

    def _coerce_row(self, table: str, row: Any) -> dict[str, Any]:
        return _coerce_export_row(table, row)

    def iter_records(self, table: str) -> Iterator[dict[str, Any]]:
        raw = self.tables.get(table, [])
        for row in raw:
            yield self._coerce_row(table, row)

    def get_records(self, table: str) -> list[dict[str, Any]]:
        return list(self.iter_records(table))

    def fetchall(self, sql: str, params: tuple = ()) -> list[tuple]:
        if params:
            raise NotImplementedError('Parameterized legacy export queries are not supported')
        table = LEGACY_SQL_TABLE_MAP.get(_normalize_sql(sql))
        if table is None:
            raise ValueError(f'Unsupported legacy export query: {sql}')
        columns = TABLE_COLUMNS[table]
        return [
            tuple(record.get(column) for column in columns)
            for record in self.get_records(table)
        ]


def open_legacy_source(
    *,
    legacy_db_url: str | None = None,
    export_file: str | Path | None = None,
    export_dir: str | Path | None = None,
) -> LegacySource:
    path_raw = export_dir or export_file
    if path_raw:
        path = Path(path_raw)
        if path.is_dir():
            return LegacyBatchedExportSource(path)
        if path.is_file():
            return LegacyExportSource(path)
        raise FileNotFoundError(f'Legacy export path not found: {path}')
    return LegacyDatabase(
        legacy_db_url or 'sqlite:///../legacy/src/db.sqlite3'
    )


def summarize_export_source(legacy: LegacySource) -> dict[str, Any]:
    """Inspect export payload without re-parsing."""
    if isinstance(legacy, LegacyBatchedExportSource):
        return {
            'format_version': legacy.format_version,
            'exported_at': legacy.exported_at,
            'source': legacy.source,
            'export_dir': str(legacy.export_dir),
            'layout': BATCHED_EXPORT_LAYOUT,
            'table_counts': legacy.table_counts,
            'batch_count': len(legacy._batches),
        }
    if isinstance(legacy, LegacyExportSource):
        return {
            'format_version': legacy.format_version,
            'exported_at': legacy.exported_at,
            'source': legacy.source,
            'export_file': str(legacy.export_path),
            'table_counts': legacy.table_counts(),
        }
    return {'source_type': 'database', 'legacy_db_url': legacy.legacy_db_url}


def resolve_import_steps(
    *,
    skip_steps: list[str] | None = None,
    essential_only: bool = False,
) -> list[str]:
    skipped = set(skip_steps or [])
    if essential_only:
        skipped |= OPTIONAL_IMPORT_STEPS
    unknown = skipped - set(FULL_IMPORT_ORDER)
    if unknown:
        raise ValueError(f'Unknown import steps to skip: {sorted(unknown)}')
    return [step for step in FULL_IMPORT_ORDER if step not in skipped]


def write_report(report: MigrationReport) -> Path:
    reports_dir = Path(__file__).resolve().parents[2] / 'migration_reports'
    reports_dir.mkdir(exist_ok=True)
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    path = reports_dir / f'{report.step}_{timestamp}.json'
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding='utf-8')
    return path


def _parse_legacy_information(raw: Any) -> dict:
    if raw is None or raw == 'None' or raw == '"None"':
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            inner = json.loads(raw)
            if isinstance(inner, dict):
                return inner
            if inner in (None, 'None'):
                return {}
        except json.JSONDecodeError:
            pass
    return {}


def migrate_islands(island: Island, legacy: LegacySource) -> MigrationReport:
    report = MigrationReport(step='islands')
    defaults = Island.default_sao_miguel()
    flags = dict(defaults.get('feature_flags', {}))
    rows = legacy.fetchall(QUERY_VARIABLES)
    if rows:
        row = rows[0]
        if len(row) == 4:
            _, version, maps, populate_maps = row
        else:
            version, maps, populate_maps = row[0], row[1], row[2]
        flags['version'] = version
        flags['maps'] = bool(maps)
        flags['populate_maps_routes'] = bool(populate_maps)
    defaults['feature_flags'] = flags
    for key, value in defaults.items():
        setattr(island, key, value)
    island.save()
    report.updated = 1
    return report


def migrate_operators(island: Island, legacy: LegacySource) -> MigrationReport:
    report = MigrationReport(step='operators')
    with for_island(island):
        for _, name in OPERATOR_PREFIXES + (('Other', 'Other'),):
            _, created = Operator.objects.update_or_create(
                island=island,
                name=name,
                defaults={'contact': {}},
            )
            report.created += int(created)
            report.updated += int(not created)
    return report


def migrate_stops(island: Island, legacy: LegacySource) -> MigrationReport:
    report = MigrationReport(step='stops')
    rows = legacy.fetchall(QUERY_STOPS)
    with for_island(island), transaction.atomic():
        for legacy_id, name, cleaned_name, latitude, longitude in rows:
            cleaned = cleaned_name or clean_string(name)
            stop, created = Stop.objects.update_or_create(
                island=island,
                cleaned_name=cleaned,
                defaults={
                    'name': name,
                    'latitude': latitude,
                    'longitude': longitude,
                    'legacy_ref': {'table': 'app_stop', 'id': legacy_id},
                },
            )
            if created:
                report.created += 1
            else:
                report.updated += 1
    return report


def migrate_calendars(island: Island, legacy: LegacySource) -> MigrationReport:
    report = MigrationReport(step='calendars')
    with for_island(island):
        for service_type in (Calendar.WEEKDAY, Calendar.SATURDAY, Calendar.SUNDAY):
            _, created = Calendar.objects.update_or_create(
                island=island,
                service_type=service_type,
            )
            report.created += int(created)
            report.updated += int(not created)
    return report


def migrate_holidays(island: Island, legacy: LegacySource) -> MigrationReport:
    report = MigrationReport(step='holidays')
    rows = legacy.fetchall(QUERY_HOLIDAYS)
    with for_island(island), transaction.atomic():
        for legacy_id, date_value, name in rows:
            if isinstance(date_value, str):
                parsed_date = datetime.strptime(date_value[:10], '%Y-%m-%d').date()
            else:
                parsed_date = date_value
            _, created = Holiday.objects.update_or_create(
                island=island,
                date=parsed_date,
                defaults={
                    'name': name,
                    'legacy_ref': {'table': 'app_holiday', 'id': legacy_id},
                },
            )
            report.created += int(created)
            report.updated += int(not created)
    return report


def migrate_stop_groups(island: Island, legacy: LegacySource) -> MigrationReport:
    report = MigrationReport(step='stop_groups')
    rows = legacy.fetchall(QUERY_GROUPS)
    with for_island(island), transaction.atomic():
        for legacy_id, name, stops in rows:
            stop_names = [part.strip() for part in (stops or '').split(',') if part.strip()]
            _, created = StopGroup.objects.update_or_create(
                island=island,
                name=name,
                defaults={
                    'stop_names': stop_names,
                    'legacy_ref': {'table': 'app_group', 'id': legacy_id},
                },
            )
            report.created += int(created)
            report.updated += int(not created)
    return report


def migrate_lines_trips(island: Island, legacy: LegacySource) -> MigrationReport:
    report = MigrationReport(step='lines_trips')
    rows = legacy.fetchall(QUERY_ROUTES)
    with for_island(island), transaction.atomic():
        for legacy_id, route, stops_raw, type_of_day, information, disabled, likes, dislikes in rows:
            service_type = LEGACY_DAY_MAP.get(str(type_of_day).strip(), Calendar.WEEKDAY)
            calendar = Calendar.objects.get(island=island, service_type=service_type)
            operator = Operator.objects.get(island=island, name=infer_operator_name(route))
            line, _ = Line.objects.update_or_create(
                island=island,
                code=str(route).strip(),
                defaults={'operator': operator, 'disabled': bool(disabled)},
            )
            existing = Trip.objects.filter(
                island=island,
                legacy_ref__id=legacy_id,
                legacy_ref__table='app_route',
            ).first()
            if existing:
                trip = existing
                created = False
                trip.line = line
                trip.calendar = calendar
                trip.likes = likes or 0
                trip.dislikes = dislikes or 0
                trip.information = _parse_legacy_information(information)
                trip.save()
            else:
                trip = Trip.objects.create(
                    island=island,
                    line=line,
                    calendar=calendar,
                    likes=likes or 0,
                    dislikes=dislikes or 0,
                    source=Trip.SOURCE_OPERATOR,
                    information=_parse_legacy_information(information),
                    legacy_ref={'table': 'app_route', 'id': legacy_id},
                )
                created = True
            report.created += int(created)
            report.updated += int(not created)

            StopTime.objects.filter(trip=trip).delete()
            stops_dict = parse_legacy_stops(stops_raw)
            if stops_dict is None:
                report.errors.append(f'route {legacy_id}: stops parse failed')
                continue

            for sequence, (stop_name, departure_raw) in enumerate(stops_dict.items(), start=1):
                departure = parse_legacy_time(str(departure_raw))
                if departure is None:
                    report.errors.append(f'route {legacy_id}: bad time {departure_raw!r} at {stop_name}')
                    continue
                cleaned = clean_string(stop_name)
                stop = (
                    Stop.objects.filter(island=island, cleaned_name=cleaned).first()
                    or Stop.objects.filter(island=island, name=stop_name).first()
                )
                if stop is None:
                    report.errors.append(f'route {legacy_id}: unmatched stop {stop_name!r}')
                    continue
                StopTime.objects.create(
                    island=island,
                    trip=trip,
                    stop=stop,
                    sequence=sequence,
                    departure_time=departure,
                )
    return report


def migrate_ads(island: Island, legacy: LegacySource) -> MigrationReport:
    report = MigrationReport(step='ads')
    rows = legacy.fetchall(QUERY_ADS)
    with for_island(island), transaction.atomic():
        for row in rows:
            legacy_id = row[0]
            _, created = Ad.objects.update_or_create(
                island=island,
                legacy_ref={'table': 'app_ad', 'id': legacy_id},
                defaults={
                    'entity': row[1],
                    'description': row[2] or '',
                    'media': row[3],
                    'start': row[4],
                    'end': row[5],
                    'action': row[6] or '',
                    'target': row[7] or '',
                    'advertise_on': row[8],
                    'platform': row[9],
                    'status': row[10],
                    'seen': row[11] or 0,
                    'clicked': row[12] or 0,
                },
            )
            report.created += int(created)
            report.updated += int(not created)
    return report


def migrate_infos(island: Island, legacy: LegacySource) -> MigrationReport:
    report = MigrationReport(step='infos')
    rows = legacy.fetchall(QUERY_INFOS)
    with for_island(island), transaction.atomic():
        for row in rows:
            legacy_id = row[0]
            text = {
                'pt': {'title': row[1], 'message': row[2]},
                'en': {'title': row[3], 'message': row[4]},
                'es': {'title': row[5], 'message': row[6]},
                'fr': {'title': row[7], 'message': row[8]},
                'de': {'title': row[9], 'message': row[10]},
            }
            _, created = RouteInfo.objects.update_or_create(
                island=island,
                legacy_ref={'table': 'app_info', 'id': legacy_id},
                defaults={
                    'text': text,
                    'source': row[13] or '',
                    'company': row[14] or '',
                    'start': row[11],
                    'end': row[12],
                },
            )
            report.created += int(created)
            report.updated += int(not created)
    return report


def migrate_subscriptions(island: Island, legacy: LegacySource) -> MigrationReport:
    from billing.models import Subscription

    report = MigrationReport(step='subscriptions')
    rows = legacy.fetchall(QUERY_SUBSCRIPTIONS)
    with transaction.atomic():
        for legacy_id, email, is_active, verification_count, created_at, updated_at in rows:
            _, created = Subscription.objects.update_or_create(
                email=email,
                defaults={
                    'is_active': bool(is_active),
                    'verification_count': verification_count or 0,
                },
            )
            report.created += int(created)
            report.updated += int(not created)
    return report


def _import_table_records(
    legacy: LegacySource,
    *,
    table: str,
    model: type[models.Model],
    step: str,
    batch_size: int = BULK_IMPORT_BATCH_SIZE,
) -> MigrationReport:
    report = MigrationReport(step=step)
    batch: list[models.Model] = []
    use_postgres_bulk = connection.vendor == 'postgresql'

    def flush_batch() -> None:
        nonlocal batch
        if not batch:
            return
        if use_postgres_bulk and hasattr(model.objects, 'bulk_create'):
            update_fields = [
                field.name
                for field in model._meta.fields
                if field.name != 'id' and not field.auto_created
            ]
            model.objects.bulk_create(
                batch,
                batch_size=batch_size,
                update_conflicts=True,
                unique_fields=['id'],
                update_fields=update_fields,
            )
            report.updated += len(batch)
        else:
            for instance in batch:
                pk = instance.pk
                defaults = {
                    field.name: getattr(instance, field.name)
                    for field in model._meta.fields
                    if field.name != 'id' and not field.auto_created
                }
                _, created = model.objects.update_or_create(id=pk, defaults=defaults)
                report.created += int(created)
                report.updated += int(not created)
        batch = []

    for record in legacy.iter_records(table):
        pk = record.get('id')
        defaults = {key: value for key, value in record.items() if key != 'id'}
        if pk is None:
            model.objects.create(**defaults)
            report.created += 1
            continue
        batch.append(model(id=pk, **defaults))
        if len(batch) >= batch_size:
            flush_batch()

    flush_batch()
    return report


def migrate_stats(island: Island, legacy: LegacySource) -> MigrationReport:
    from analytics.models import Stat

    return _import_table_records(legacy, table='app_stat', model=Stat, step='stats')


def migrate_data(island: Island, legacy: LegacySource) -> MigrationReport:
    from legacy_archive.models import LegacyData

    return _import_table_records(legacy, table='app_data', model=LegacyData, step='data')


def migrate_legacy_trips(island: Island, legacy: LegacySource) -> MigrationReport:
    from legacy_archive.models import LegacyTrip

    return _import_table_records(legacy, table='app_trip', model=LegacyTrip, step='legacy_trips')


def migrate_legacy_tripstops(island: Island, legacy: LegacySource) -> MigrationReport:
    from legacy_archive.models import LegacyTripStop

    return _import_table_records(
        legacy, table='app_tripstop', model=LegacyTripStop, step='legacy_tripstops'
    )


def migrate_aifeedback(island: Island, legacy: LegacySource) -> MigrationReport:
    from legacy_archive.models import LegacyAIFeedback

    return _import_table_records(
        legacy, table='app_aifeedback', model=LegacyAIFeedback, step='aifeedback'
    )


def migrate_emailopens(island: Island, legacy: LegacySource) -> MigrationReport:
    from legacy_archive.models import LegacyEmailOpen

    return _import_table_records(
        legacy, table='app_emailopen', model=LegacyEmailOpen, step='emailopens'
    )


MIGRATION_STEPS: dict[str, Any] = {
    'islands': migrate_islands,
    'operators': migrate_operators,
    'stops': migrate_stops,
    'stop_groups': migrate_stop_groups,
    'calendars': migrate_calendars,
    'holidays': migrate_holidays,
    'lines_trips': migrate_lines_trips,
    'infos': migrate_infos,
    'ads': migrate_ads,
    'subscriptions': migrate_subscriptions,
    'stats': migrate_stats,
    'data': migrate_data,
    'legacy_trips': migrate_legacy_trips,
    'legacy_tripstops': migrate_legacy_tripstops,
    'aifeedback': migrate_aifeedback,
    'emailopens': migrate_emailopens,
}


def run_migration_step(
    step: str,
    island: Island,
    *,
    legacy_db_url: str | None = None,
    export_file: str | Path | None = None,
    legacy: LegacySource | None = None,
) -> MigrationReport:
    if step not in MIGRATION_STEPS:
        raise ValueError(f'Unknown migration step: {step}')
    if legacy is None:
        legacy = open_legacy_source(legacy_db_url=legacy_db_url, export_file=export_file)
    report = MIGRATION_STEPS[step](island, legacy)
    write_report(report)
    return report


def run_full_import(
    island: Island,
    *,
    legacy_db_url: str | None = None,
    export_file: str | Path | None = None,
    dry_run: bool = False,
    legacy: LegacySource | None = None,
    steps: list[str] | None = None,
    skip_steps: list[str] | None = None,
    essential_only: bool = False,
    on_step_start: Callable[[str], None] | None = None,
    on_step_complete: Callable[[MigrationReport], None] | None = None,
) -> list[MigrationReport]:
    order = steps or resolve_import_steps(skip_steps=skip_steps, essential_only=essential_only)
    reports: list[MigrationReport] = []
    if dry_run:
        logger.info('Dry run — would execute steps: %s', order)
        return reports

    if legacy is None:
        legacy = open_legacy_source(legacy_db_url=legacy_db_url, export_file=export_file)

    for step in order:
        if on_step_start:
            on_step_start(step)
        report = MIGRATION_STEPS[step](island, legacy)
        write_report(report)
        reports.append(report)
        if on_step_complete:
            on_step_complete(report)
    return reports
