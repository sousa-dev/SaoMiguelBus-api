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
    StopAlias,
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

# Trips are seeded with a positive vote balance on CREATE only.
#
# `search_routes` prefixes a route code with 'C' (unconfirmed) when its like
# ratio is below 60%, and a trip with no votes scores 0. Without a head start,
# every single AzoresBus route would be marked unconfirmed on day one -- a
# network-wide UI regression the moment the cutover lands (02 §3.8).
#
# These timetables come from the operator's own feed, so treating them as
# unverified user-submitted data is simply wrong. 5/0 puts them at 100%, well
# clear of the threshold, while leaving real votes able to move the number.
#
# On UPDATE these fields are never touched: a re-sync must not erase votes users
# have actually cast.
SEED_LIKES = 5
SEED_DISLIKES = 0

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
        (
            stop_by_external_id,
            report['stops'],
            report['flagged_stop_groups'],
            report['naming'],
        ) = _import_stops(island, stops)
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


def _reconcile_stop(island, group) -> Stop:
    """Find this group's existing Stop row and RENAME it, rather than orphaning it.

    `Stop` carries no upstream id -- `cleaned_name` is its only identity. So
    the naive `update_or_create(cleaned_name=canonical)` would, on the first
    canonical sync, create 437 new rows and strand the old ones: nothing
    prunes them, and `_rebuild_stop_times` only reruns for trips whose
    `payload_hash` changed, so most StopTimes would keep pointing at the
    strays indefinitely. Half the network on one row, half on another.

    Matching on the poles' VERBATIM names instead finds the pre-rename row and
    renames it in place, which preserves `Stop.pk` -- and `Stop.pk` is what
    mobile favourites, `/transit/stop/:id` links, `AtlasPoi.external_refs` and
    the offline bundle's stop indices are all built on.

    Being in the sync rather than only in a data migration is deliberate: it
    makes the rename self-healing and order-independent, so a half-applied
    deploy repairs itself on the next run.
    """
    cleaned = clean_string(group.name)
    scoped = Stop.objects.filter(island=island, dataset=DATASET_AZORESBUS)

    stop = scoped.filter(cleaned_name=cleaned).first()

    legacy_folds = {clean_string(m['name']) for m in group.members} - {cleaned}
    previous = list(scoped.filter(cleaned_name__in=legacy_folds)) if legacy_folds else []

    if stop is None and previous:
        stop = previous.pop(0)

    # Two upstream spellings of one road pair converging on one canonical name
    # (`S. ROQUE (BARRACUDA)` / `SÃO ROQUE (BARRACUDA)`). Repoint before
    # deleting: StopTime.stop is PROTECT, so the delete fails otherwise.
    for loser in previous:
        if loser.pk == stop.pk:
            continue
        StopTime.objects.filter(stop=loser).update(stop=stop)
        ExternalStop.objects.filter(stop=loser).update(stop=stop)
        loser.delete()

    if stop is None:
        return Stop.objects.create(
            island=island,
            dataset=DATASET_AZORESBUS,
            cleaned_name=cleaned,
            name=group.name,
            latitude=group.latitude,
            longitude=group.longitude,
        )

    stop.name = group.name
    stop.cleaned_name = cleaned
    stop.latitude = group.latitude
    stop.longitude = group.longitude
    stop.save(update_fields=['name', 'cleaned_name', 'latitude', 'longitude'])
    return stop


def _sync_stop_aliases(island, aliases_by_stop: dict[int, set[str]]) -> int:
    """Persist every folded spelling that must keep resolving to a stop.

    An alias that collides with some other stop's real `cleaned_name`, or that
    two stops both claim, is DROPPED rather than guessed at -- a wrong alias
    silently sends a user to the wrong village, which is worse than a query
    that falls through to the existing prefix fallback.
    """
    real_names = set(
        Stop.objects.filter(island=island, dataset=DATASET_AZORESBUS)
        .values_list('cleaned_name', flat=True)
    )
    claims: dict[str, set[int]] = {}
    for stop_id, aliases in aliases_by_stop.items():
        for alias in aliases - real_names:
            claims.setdefault(alias, set()).add(stop_id)

    written = 0
    for alias, stop_ids in claims.items():
        if len(stop_ids) > 1:
            logger.info(
                'azoresbus import: alias %r claimed by %s stops, dropped',
                alias, len(stop_ids),
            )
            continue
        StopAlias.objects.update_or_create(
            island=island,
            dataset=DATASET_AZORESBUS,
            cleaned_alias=alias,
            defaults={'stop_id': next(iter(stop_ids))},
        )
        written += 1
    return written


def _import_stops(island, payload: list[dict]):
    """1456 poles -> 814 Stop rows + 1456 ExternalStop rows.

    Names are canonicalized inside `collapse_stops`, so `Stop.name` is the
    expanded, title-cased form while `ExternalStop.name` stays verbatim -- the
    audit trail, and the source of the aliases that keep old links alive.
    """
    collapsed = collapse_stops(payload)
    stop_by_external_id: dict[str, ExternalStop] = {}
    aliases_by_stop: dict[int, set[str]] = {}

    for group in collapsed.groups:
        stop = _reconcile_stop(island, group)
        aliases_by_stop.setdefault(stop.id, set()).update(
            clean_string(member['name']) for member in group.members
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

    _sync_stop_aliases(island, aliases_by_stop)

    if collapsed.ambiguous_areas:
        logger.warning(
            'azoresbus import: %s area(s) span further than any village should, '
            'left for curation in services_names.VILLAGE_OVERRIDES: %s',
            len(collapsed.ambiguous_areas),
            ', '.join(
                f'{a.name} ({a.span_m / 1000:.1f}km, '
                f'{"unmerged" if a.unmerged else "upstream spelling"})'
                for a in collapsed.ambiguous_areas
            ),
        )
    if collapsed.unexpanded:
        logger.warning(
            'azoresbus import: unknown abbreviations survived canonicalization, '
            'add them to services_names.ABBREVIATIONS: %s',
            ', '.join(collapsed.unexpanded),
        )

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
        {
            'ambiguous_areas': [a.as_dict() for a in collapsed.ambiguous_areas],
            'unexpanded_tokens': collapsed.unexpanded,
        },
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
                likes=SEED_LIKES,
                dislikes=SEED_DISLIKES,
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
