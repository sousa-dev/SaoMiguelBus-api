"""AUTH_KEY-protected AzoresBus ops endpoints.

Support for manually driving a schedule sync and inspecting its effect:
`snapshot` fingerprints the current timetable so a before/after diff can be
taken around a `sync` call, without needing direct DB access.
"""

from __future__ import annotations

import hashlib

from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from tenancy.models import Island
from tenancy.services import for_island
from transit.models import DATASET_AZORESBUS, Line, StopTime, Trip


def _auth_key_from_request(request: Request) -> str:
    return (
        request.query_params.get('key')
        or request.headers.get('X-Auth-Key')
        or request.headers.get('X-Api-Key')
        or ''
    )


def _require_auth_key(request: Request) -> Response | None:
    if _auth_key_from_request(request) != settings.AUTH_KEY:
        return Response({'error': 'Unauthorized'}, status=401)
    return None


def _resolve_island(request: Request) -> tuple[Island | None, Response | None]:
    island_key = (request.query_params.get('island') or 'sao-miguel').strip()
    try:
        return Island.objects.get(key=island_key), None
    except Island.DoesNotExist:
        return None, Response(
            {'error': f'Unknown island key: {island_key}'}, status=400,
        )


def _line_checksum(line_id: int) -> str:
    """Sha1 over every (trip, stop, sequence, times) row for one line.

    Cheap and order-independent (sorted before hashing) so a sync that
    changes even one departure time flips the checksum without needing to
    diff full row lists over HTTP.
    """
    rows = (
        StopTime.objects.filter(trip__line_id=line_id)
        .order_by('trip_id', 'sequence')
        .values_list(
            'trip_id', 'sequence', 'departure_time', 'arrival_time', 'day_offset',
        )
    )
    digest = hashlib.sha1()
    for row in rows:
        digest.update('|'.join(str(part) for part in row).encode())
        digest.update(b'\n')
    return digest.hexdigest()


@api_view(['GET'])
@permission_classes([AllowAny])
def azoresbus_snapshot_view(request: Request) -> Response:
    """
    Fingerprint the AzoresBus timetable currently stored in the DB.

    Query params:
      - key / X-Auth-Key: AUTH_KEY (required)
      - island: island key slug (default sao-miguel)

    Returns per-line trip/stop-time counts and a checksum, plus totals and
    the most recent sync run, so two calls around a `sync` can be diffed.
    """
    denied = _require_auth_key(request)
    if denied:
        return denied

    island, err = _resolve_island(request)
    if err:
        return err

    from azoresbus.models import SyncRun

    with for_island(island):
        lines = list(
            Line.objects.filter(island=island, dataset=DATASET_AZORESBUS)
            .order_by('code')
        )
        line_snapshots = []
        for line in lines:
            trip_count = Trip.objects.filter(
                island=island, dataset=DATASET_AZORESBUS, line=line,
            ).count()
            stop_time_count = StopTime.objects.filter(
                trip__island=island, trip__dataset=DATASET_AZORESBUS, trip__line=line,
            ).count()
            line_snapshots.append({
                'code': line.code,
                'name': line.display_name,
                'disabled': line.disabled,
                'tripCount': trip_count,
                'stopTimeCount': stop_time_count,
                'checksum': _line_checksum(line.id) if trip_count else '',
            })

        total_trips = Trip.objects.filter(
            island=island, dataset=DATASET_AZORESBUS,
        ).count()
        total_stop_times = StopTime.objects.filter(
            trip__island=island, trip__dataset=DATASET_AZORESBUS,
        ).count()

        last_run = (
            SyncRun.objects.filter(
                island=island, kind=SyncRun.KIND_SCHEDULES,
            )
            .order_by('-started_at')
            .first()
        )

    return Response({
        'ok': True,
        'island': island.key,
        'dataset': DATASET_AZORESBUS,
        'totals': {
            'lines': len(lines),
            'trips': total_trips,
            'stopTimes': total_stop_times,
        },
        'lines': line_snapshots,
        'lastSyncRun': {
            'id': last_run.id,
            'status': last_run.status,
            'startedAt': last_run.started_at.isoformat(),
            'finishedAt': last_run.finished_at.isoformat() if last_run.finished_at else None,
            'requestCount': last_run.request_count,
            'stats': last_run.stats,
        } if last_run else None,
    })


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def azoresbus_trigger_sync_view(request: Request) -> Response:
    """
    Queue (or run) an AzoresBus schedule sync for debugging / manual refresh.

    Query params:
      - key / X-Auth-Key: AUTH_KEY (required)
      - island: island key slug (default sao-miguel)
      - full: true to include the far-season week (default false)
      - async: false to run inline and block for the result (default true --
        a full run can take many minutes and would exceed the request's
        socket timeout)
    """
    denied = _require_auth_key(request)
    if denied:
        return denied

    island, err = _resolve_island(request)
    if err:
        return err

    full = request.query_params.get('full', 'false').lower() in ('1', 'true', 'yes')
    run_async = request.query_params.get('async', 'true').lower() not in (
        '0', 'false', 'no',
    )

    if run_async:
        from azoresbus.tasks import queue_sync

        result = queue_sync(island_key=island.key, full=full)
        return Response({'ok': bool(result.get('queued')), 'async': True, **result})

    from azoresbus.services_sync import SyncAborted, run_sync

    try:
        with for_island(island):
            report = run_sync(island, full=full)
    except SyncAborted as exc:
        return Response({'ok': False, 'async': False, 'error': str(exc)}, status=502)

    return Response({'ok': True, 'async': False, **report})
