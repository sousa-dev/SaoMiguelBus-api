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
from typing import Any
from urllib.parse import urlparse

from django.db import connection, transaction
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


def write_report(report: MigrationReport) -> Path:
    reports_dir = Path(__file__).resolve().parents[2] / 'migration_reports'
    reports_dir.mkdir(exist_ok=True)
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    path = reports_dir / f'{report.step}_{timestamp}.json'
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding='utf-8')
    return path


def migrate_islands(island: Island, legacy: LegacyDatabase) -> MigrationReport:
    report = MigrationReport(step='islands')
    defaults = Island.default_sao_miguel()
    for key, value in defaults.items():
        setattr(island, key, value)
    island.save()
    report.updated = 1
    return report


def migrate_operators(island: Island, legacy: LegacyDatabase) -> MigrationReport:
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


def migrate_stops(island: Island, legacy: LegacyDatabase) -> MigrationReport:
    report = MigrationReport(step='stops')
    rows = legacy.fetchall(
        'SELECT id, name, cleaned_name, latitude, longitude FROM app_stop ORDER BY id'
    )
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


def migrate_calendars(island: Island, legacy: LegacyDatabase) -> MigrationReport:
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


def migrate_holidays(island: Island, legacy: LegacyDatabase) -> MigrationReport:
    report = MigrationReport(step='holidays')
    rows = legacy.fetchall('SELECT id, date, name FROM app_holiday ORDER BY date')
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


def migrate_stop_groups(island: Island, legacy: LegacyDatabase) -> MigrationReport:
    report = MigrationReport(step='stop_groups')
    rows = legacy.fetchall('SELECT id, name, stops FROM app_group ORDER BY id')
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


def migrate_lines_trips(island: Island, legacy: LegacyDatabase) -> MigrationReport:
    report = MigrationReport(step='lines_trips')
    rows = legacy.fetchall(
        'SELECT id, route, stops, type_of_day, information, disabled, likes, dislikes '
        'FROM app_route ORDER BY id'
    )
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
                trip.save()
            else:
                trip = Trip.objects.create(
                    island=island,
                    line=line,
                    calendar=calendar,
                    likes=likes or 0,
                    dislikes=dislikes or 0,
                    source=Trip.SOURCE_OPERATOR,
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


def migrate_ads(island: Island, legacy: LegacyDatabase) -> MigrationReport:
    report = MigrationReport(step='ads')
    rows = legacy.fetchall(
        'SELECT id, entity, description, media, start, end, action, target, '
        'advertise_on, platform, status, seen, clicked FROM app_ad ORDER BY id'
    )
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


MIGRATION_STEPS: dict[str, Any] = {
    'islands': migrate_islands,
    'operators': migrate_operators,
    'stops': migrate_stops,
    'stop_groups': migrate_stop_groups,
    'calendars': migrate_calendars,
    'holidays': migrate_holidays,
    'lines_trips': migrate_lines_trips,
    'ads': migrate_ads,
}


def run_migration_step(step: str, island: Island, legacy_db_url: str) -> MigrationReport:
    if step not in MIGRATION_STEPS:
        raise ValueError(f'Unknown migration step: {step}')
    legacy = LegacyDatabase(legacy_db_url)
    report = MIGRATION_STEPS[step](island, legacy)
    write_report(report)
    return report


def run_full_import(island: Island, legacy_db_url: str, *, dry_run: bool = False) -> list[MigrationReport]:
    order = [
        'islands',
        'operators',
        'stops',
        'stop_groups',
        'calendars',
        'holidays',
        'lines_trips',
        'ads',
    ]
    reports: list[MigrationReport] = []
    if dry_run:
        logger.info('Dry run — would execute steps: %s', order)
        return reports
    for step in order:
        reports.append(run_migration_step(step, island, legacy_db_url))
    return reports
