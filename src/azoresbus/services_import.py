"""Write fetched upstream payloads into transit models.

Deliberately takes already-fetched data rather than a client: the fetching is
bounded and rate-limited elsewhere, and keeping the write path pure means the
whole import is testable against committed fixtures with no network.

Everything written here is `dataset='azoresbus'`. Legacy rows are never read,
updated or deleted by this module.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date

from django.db import transaction

from azoresbus.models import (
    ExternalJourney,
    ExternalStop,
    ServiceObservation,
    SyncRun,
)
from azoresbus.services_calendar import (
    build_observation_matrix,
    circulations_to_stop_times,
    derive_patterns,
)
from azoresbus.services_stops import collapse_stops
from transit.models import (
    DATASET_AZORESBUS,
    Line,
    Operator,
    ServicePattern,
    Stop,
    StopTime,
    Trip,
)
from transit.services.legacy_import import clean_string
from transit.services.offline_bundle import (
    bump_data_revision,
    suppress_revision_bumps,
)

logger = logging.getLogger(__name__)

OPERATOR_NAME = 'AzoresBus'

WEEKDAY_FIELDS = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday',
                  'saturday', 'sunday')


def import_schedules(
    island,
    *,
    run: SyncRun,
    stops: list[dict],
    routes: list[dict],
    journeys: dict[tuple[str, date], list[dict]],
    details: dict[str, dict],
    sampled_dates: list[date],
    holidays: set[date],
) -> dict:
    """Upsert an entire AzoresBus sample. Idempotent.

    One transaction with revision bumps suppressed, so ~1200 trip writes do not
    each invalidate the offline bundle; a single bump lands at the end. This is
    the pattern the legacy import already uses.
    """
    report: dict = {}

    with transaction.atomic(), suppress_revision_bumps():
        operator = _ensure_operator(island)
        stop_by_external_id, report['stops'], report['flagged_stop_groups'] = (
            _import_stops(island, stops)
        )
        line_by_route_id, report['lines'] = _import_lines(
            island, routes, operator,
        )

        matrix = build_observation_matrix(
            {key: [j['id'] for j in value] for key, value in journeys.items()}
        )
        rules = derive_patterns(
            matrix, sampled_dates=sampled_dates, holidays=holidays,
        )
        patterns, report['patterns'] = _import_patterns(island, rules, run)

        report['trips'] = _import_journeys(
            island, journeys, details, line_by_route_id,
            stop_by_external_id, patterns, rules,
        )
        report['observations'] = _record_observations(island, matrix, run)
        report['journey_count'] = len(matrix)

    bump_data_revision(island.id)
    return report


# -- pieces ----------------------------------------------------------------


def _ensure_operator(island) -> Operator:
    """AzoresBus lines get their own operator.

    `infer_operator_name` maps legacy route-code prefixes and returns 'Other'
    for anything unrecognised, so routing 55 AzoresBus codes through it would
    file the entire network under 'Other' (02 §3.8).
    """
    operator, _ = Operator.objects.get_or_create(
        island=island, name=OPERATOR_NAME, defaults={'contact': {}},
    )
    return operator


def _import_stops(island, payload: list[dict]):
    """1456 poles -> 816 Stop rows + 1456 ExternalStop rows."""
    collapsed = collapse_stops(payload)
    stop_by_external_id: dict[str, ExternalStop] = {}

    for group in collapsed.groups:
        stop, _ = Stop.objects.update_or_create(
            island=island,
            dataset=DATASET_AZORESBUS,
            cleaned_name=clean_string(group.name),
            defaults={
                'name': group.name,
                'latitude': group.latitude,
                'longitude': group.longitude,
            },
        )
        for member in group.members:
            external, _ = ExternalStop.objects.update_or_create(
                island=island,
                dataset=DATASET_AZORESBUS,
                external_id=str(member['id']),
                defaults={
                    'code': str(member['nameShort']),
                    'name': member['name'],
                    'latitude': float(member['position']['lat']),
                    'longitude': float(member['position']['lon']),
                    'stop': stop,
                },
            )
            stop_by_external_id[str(member['id'])] = external

    if collapsed.flagged:
        logger.info(
            'azoresbus import: %s stop groups span more than 75m: %s',
            len(collapsed.flagged),
            ', '.join(f'{g.name} ({g.span_m:.0f}m)' for g in collapsed.flagged),
        )

    return (
        stop_by_external_id,
        len(collapsed.groups),
        [
            {'name': g.name, 'span_m': round(g.span_m, 1)}
            for g in collapsed.flagged
        ],
    )


def _import_lines(island, routes: list[dict], operator: Operator):
    """Every listed route becomes a Line.

    `isActive` is NOT consulted: it is a display flag, and honouring it drops
    line 328 (weekend-only, ids 942-945) entirely, plus the four school-term
    lines (98 B5).
    """
    line_by_route_id: dict[str, Line] = {}
    for route in routes:
        line, _ = Line.objects.update_or_create(
            island=island,
            dataset=DATASET_AZORESBUS,
            code=str(route['nameShort']),
            defaults={
                'operator': operator,
                'display_name': route.get('name', ''),
                'disabled': False,
            },
        )
        line_by_route_id[str(route['id'])] = line
    return line_by_route_id, len(line_by_route_id)


def _import_patterns(island, rules, run: SyncRun):
    """One ServicePattern per distinct rule, shared by every journey with it."""
    patterns: dict[str, ServicePattern] = {}
    for rule in rules.values():
        if rule.key in patterns:
            continue
        pattern, _ = ServicePattern.objects.update_or_create(
            island=island,
            dataset=DATASET_AZORESBUS,
            key=rule.key,
            defaults={
                **{
                    name: (index in rule.weekdays)
                    for index, name in enumerate(WEEKDAY_FIELDS)
                },
                'start_date': rule.start_date,
                'end_date': rule.end_date,
                'end_unknown': rule.end_unknown,
                'ambiguous_weekdays': sorted(rule.ambiguous_weekdays),
                'confidence': rule.confidence,
                'derived_from_run': run,
            },
        )
        patterns[rule.key] = pattern
    return patterns, len(patterns)


def _import_journeys(
    island, journeys, details, line_by_route_id,
    stop_by_external_id, patterns, rules,
):
    """One Trip per upstream journey, with its stop times rebuilt."""
    route_for_journey: dict[str, str] = {}
    listing_for_journey: dict[str, dict] = {}
    for (route_id, _day), rows in journeys.items():
        for row in rows:
            route_for_journey[str(row['id'])] = route_id
            listing_for_journey[str(row['id'])] = row

    written = 0
    for journey_id, detail in details.items():
        route_id = route_for_journey.get(journey_id)
        line = line_by_route_id.get(route_id)
        if line is None:
            continue

        listing = listing_for_journey.get(journey_id, {})
        rule = rules.get(journey_id)
        pattern = patterns.get(rule.key) if rule else None

        payload_hash = hashlib.sha256(
            json.dumps(detail, sort_keys=True).encode('utf-8')
        ).hexdigest()
        identity = (
            f'{line.code}|{listing.get("start", "")}|{listing.get("end", "")}'
        )

        external = ExternalJourney.objects.filter(
            island=island, dataset=DATASET_AZORESBUS, external_id=journey_id,
        ).first()

        if external is None:
            trip = Trip.objects.create(
                island=island,
                dataset=DATASET_AZORESBUS,
                line=line,
                calendar=None,
                service=pattern,
                source=Trip.SOURCE_OPERATOR,
                headsign=listing.get('name', '') or '',
                direction=str(detail.get('direction', '')),
            )
            external = ExternalJourney.objects.create(
                island=island,
                dataset=DATASET_AZORESBUS,
                external_id=journey_id,
                route_ext_id=route_id,
                direction=int(detail.get('direction') or 0),
                shape=detail.get('shape', '') or '',
                payload_hash=payload_hash,
                identity=identity,
                trip=trip,
            )
        else:
            trip = external.trip
            trip.line = line
            trip.service = pattern
            trip.headsign = listing.get('name', '') or ''
            trip.save(update_fields=['line', 'service', 'headsign'])

            if external.identity and external.identity != identity:
                # A journey id whose meaning changed. Not fatal, but it is the
                # republish signature and must be visible (98 §7).
                logger.warning(
                    'azoresbus journey %s changed identity: %s -> %s',
                    journey_id, external.identity, identity,
                )

            unchanged = external.payload_hash == payload_hash
            external.route_ext_id = route_id
            external.shape = detail.get('shape', '') or ''
            external.payload_hash = payload_hash
            external.identity = identity
            external.save()
            if unchanged:
                # The hash skips the StopTime rebuild, never the GET: the
                # listing has no circulations, so the hash is only knowable
                # after fetching the detail (98 §4 gap).
                written += 1
                continue

        _rebuild_stop_times(island, trip, detail, stop_by_external_id)
        written += 1

    return written


def _rebuild_stop_times(island, trip, detail, stop_by_external_id) -> None:
    StopTime.objects.filter(trip=trip).delete()
    rows = []
    for row in circulations_to_stop_times(detail.get('circulations') or []):
        stage = row.get('stage') or {}
        external = stop_by_external_id.get(str(stage.get('id')))
        if external is None:
            continue
        rows.append(StopTime(
            island=island,
            trip=trip,
            stop=external.stop,
            external_stop=external,
            sequence=row['sequence'],
            departure_time=row['departure_time'],
            arrival_time=row.get('arrival_time'),
            day_offset=row['day_offset'],
        ))
    StopTime.objects.bulk_create(rows)


def _record_observations(island, matrix, run: SyncRun) -> int:
    """The raw evidence, kept so patterns can be re-derived without re-fetching."""
    written = 0
    for journey_id, days in matrix.items():
        for day in days:
            _, created = ServiceObservation.objects.update_or_create(
                island=island,
                dataset=DATASET_AZORESBUS,
                external_id=journey_id,
                date=day,
                defaults={'run': run},
            )
            written += int(created)
    return written
