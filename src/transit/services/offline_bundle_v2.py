"""Schema-versioned offline bundle. ONE network per bundle (00 Decision 4).

The current endpoint cannot carry this shape. `offlineSearch` in shipped builds
has no `dataset` concept and `indexOf`s every row, so emitting two networks in
the existing payload would hand old clients legacy and AzoresBus interleaved
(98 B3). Only builds carrying the mobile plan request this one.

`services` replaces `weekday`. A WEEKDAY|SAT|SUN enum cannot express line 112
(Tue/Thu) or 307's seasonal flip, so the client evaluates the SAME rule the
server does against an ISO date — which is what `holidays` is for.

The bundle carries one server-resolved network plus `cutoverAt`, and the client
uses those only to detect that a pre-cutover bundle has EXPIRED, never to filter
rows. Shipping one network halves an unmeasured payload against a shared 6 MB
budget and fails loudly instead of silently when the clock is wrong.
"""

from __future__ import annotations

import hashlib

from django.utils import timezone

from transit.models import Holiday, ServicePattern, Stop, StopTime, Trip
from transit.services.offline_bundle import get_data_revision
from transit.services.schedule_phase import (
    cutover_at,
    next_transition_at,
    resolve_dataset,
    schedule_phase,
)

SCHEMA_VERSION = 2

WEEKDAY_FIELDS = ServicePattern.WEEKDAY_FIELDS


def compute_version_v2(island) -> str:
    """Folds in what the v1 fingerprint misses.

    `island.key:revision:stops:routes` does not change on a phase flip or a term
    boundary, so a cached bundle would survive the cutover (98 §6). Dataset,
    cutover instant and the service-window identity all participate.
    """
    dataset = resolve_dataset(island)
    cutover = cutover_at(island)
    stops = Stop.objects.filter(dataset=dataset).count()
    trips = Trip.objects.filter(
        dataset=dataset, source=Trip.SOURCE_OPERATOR,
    ).count()
    window = (
        ServicePattern.objects.filter(dataset=dataset)
        .order_by('-start_date')
        .values_list('start_date', flat=True)
        .first()
    )
    raw = ':'.join([
        island.key,
        str(get_data_revision(island)),
        dataset,
        str(stops),
        str(trips),
        cutover.isoformat() if cutover else '',
        window.isoformat() if window else '',
    ])
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]


def build_offline_bundle_v2(island) -> dict:
    dataset = resolve_dataset(island)
    cutover = cutover_at(island)
    transition = next_transition_at(island)

    stops = list(
        Stop.objects.filter(dataset=dataset).order_by('id')
        .values('id', 'name', 'latitude', 'longitude')
    )
    stop_index = {row['id']: position for position, row in enumerate(stops)}

    services: dict[str, dict] = {}
    for pattern in ServicePattern.objects.filter(dataset=dataset).prefetch_related(
        'exceptions',
    ):
        added, removed = [], []
        for exception in pattern.exceptions.all():
            target = added if exception.exception_type == 1 else removed
            target.append(exception.date.isoformat())
        services[pattern.key] = {
            'days': ''.join(
                '1' if getattr(pattern, name) else '0'
                for name in WEEKDAY_FIELDS
            ),
            'from': pattern.start_date.isoformat() if pattern.start_date else None,
            'to': pattern.end_date.isoformat() if pattern.end_date else None,
            'added': sorted(added),
            'removed': sorted(removed),
        }

    routes = []
    trips = (
        Trip.objects.filter(dataset=dataset, source=Trip.SOURCE_OPERATOR)
        .exclude(line__disabled=True)
        .select_related('line', 'service')
    )
    for trip in trips:
        rows = list(
            StopTime.objects.filter(trip=trip)
            .select_related('external_stop')
            .order_by('sequence')          # never a bare TimeField (98 B2)
        )
        if not rows:
            continue
        routes.append({
            'id': trip.id,
            'line': trip.line.code,
            'service': trip.service.key if trip.service_id else None,
            'stops': [stop_index.get(row.stop_id) for row in rows],
            'codes': [
                row.external_stop.code if row.external_stop_id else None
                for row in rows
            ],
            'times': [
                row.departure_time.hour * 3600
                + row.departure_time.minute * 60
                + row.departure_time.second
                for row in rows
            ],
            # The night wrap, so offline ordering matches the server's.
            'offsets': [row.day_offset for row in rows],
        })

    return {
        'schema': SCHEMA_VERSION,
        'version': compute_version_v2(island),
        'generatedAt': timezone.now().isoformat(),
        'island': island.key,
        'dataset': dataset,
        'cutoverAt': cutover.isoformat() if cutover else None,
        'nextTransitionAt': transition.isoformat() if transition else None,
        'phase': schedule_phase(island),
        # Must span the dates the services rules cover: emitting a list that
        # stops in 2025 breaks the client's holiday->Sunday branch for every
        # date that matters (00 prerequisite).
        'holidays': [
            {'date': holiday.date.isoformat(), 'name': holiday.name}
            for holiday in Holiday.objects.filter(island=island).order_by('date')
        ],
        'stops': stops,
        'services': services,
        'routes': routes,
    }
