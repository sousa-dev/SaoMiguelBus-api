"""Sync worker: upstream sample -> transit models.

The dangerous part of a sync is not the fetching, it is deciding that something
has gone away. A 200 with a partial list looks exactly like a deletion
(02 §4.5), and a term/summer split makes "absent" the normal state for half the
network for half the year (98 B0).

So service is RETIRED, not deleted: the sync closes a journey's service window
and leaves the trip, its id, its votes and its observation history in place. If
the service comes back, a new observation reopens it. Hard deletion is reserved
for rows no observation references at all, and sits behind the same gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from decouple import config


AZORESBUS_SYNC_PRUNE_FLOOR = config(
    'AZORESBUS_SYNC_PRUNE_FLOOR', default=0.10, cast=float,
)


class SyncAborted(Exception):
    """The run stopped without completing. Never retires anything."""


@dataclass
class RetirementDecision:
    """Whether this run has earned the right to remove service, and why."""

    allowed: bool
    reason: str = ''
    scope_dates: set[date] = field(default_factory=set)

    def as_dict(self) -> dict:
        """Serialisable for SyncRun.stats -- the decision must be auditable."""
        return {
            'allowed': self.allowed,
            'reason': self.reason,
            'scope_dates': sorted(day.isoformat() for day in self.scope_dates),
        }


def evaluate_retirement(
    *,
    status: str,
    journey_count: int,
    previous_journey_count: int | None,
    sampled_dates: list[date],
    far_season_dates: list[date],
    floor: float | None = None,
) -> RetirementDecision:
    """Gate every rule in 02 §4.5 before any service window is closed.

    Ordered so the cheapest and most decisive checks fail first, and so the
    reason returned is the most useful one rather than merely the first.
    """
    floor = AZORESBUS_SYNC_PRUNE_FLOOR if floor is None else floor
    scope = set(sampled_dates) | set(far_season_dates)

    if status != 'completed':
        return RetirementDecision(
            False,
            f'run status is {status!r}, not completed -- a budget cap, abort or '
            'failure streak leaves a partial picture',
            scope,
        )

    if not journey_count:
        return RetirementDecision(
            False,
            'the sample came back empty network-wide, which is an upstream '
            'problem and not a deletion',
            scope,
        )

    if previous_journey_count is None:
        return RetirementDecision(
            False,
            'no successful previous run to use as a baseline, so nothing this '
            'run did not see is evidence of removal',
            scope,
        )

    if not far_season_dates:
        # 98 B0: 307 loses five school runs in summer, 112/321/324/325 vanish
        # entirely. Without the contrast they all look deleted.
        return RetirementDecision(
            False,
            'no far season observations, so "out of season" cannot be told '
            'from "gone"',
            scope,
        )

    minimum = previous_journey_count * (1.0 - floor)
    if journey_count < minimum:
        return RetirementDecision(
            False,
            f'journey count {journey_count} is below the floor '
            f'({minimum:.0f} = {1 - floor:.0%} of {previous_journey_count})',
            scope,
        )

    return RetirementDecision(
        True,
        f'{journey_count} journeys across {len(scope)} sampled dates, '
        f'within {floor:.0%} of the previous {previous_journey_count}',
        scope,
    )


# -- the run itself ---------------------------------------------------------


def run_sync(
    island,
    *,
    full: bool = False,
    dates=None,
    no_prune: bool = False,
    max_requests: int | None = None,
) -> dict:
    """Fetch, import, and decide about retirement. One SyncRun row per call.

    Lives here rather than in the management command so the Celery task — which
    is what the deploy bootstrap, the beat schedules and the staleness backstop
    all use — runs exactly the same code path as a hand-run command.
    """
    from datetime import date as date_cls

    from django.utils import timezone

    from azoresbus.client import AzoresbusClient, AzoresbusError
    from azoresbus.models import ServiceObservation, SyncRun
    from azoresbus.services_import import import_schedules
    from azoresbus.services_sampling import build_sample
    from transit.models import DATASET_AZORESBUS, Holiday
    from transit.services.schedule_phase import today_in_azores

    holidays = set(
        Holiday.objects.filter(island=island).values_list('date', flat=True)
    )
    today = today_in_azores()
    if not any(day.year == today.year for day in holidays):
        raise SyncAborted(
            f'No Holiday rows for {today.year}. Refusing to derive patterns: '
            'sampling through an empty holiday year records Sunday sets as '
            'weekday service (98 B6).'
        )

    if dates:
        sample_dates, near, far = list(dates), list(dates), []
        no_prune = True
    else:
        # No stored far-season evidence => upgrade to a full run, or the first
        # retirement pass cannot tell "out of season" from "deleted" (02 §4.1).
        has_far = ServiceObservation.objects.filter(
            island=island, dataset=DATASET_AZORESBUS,
        ).exists()
        sample = build_sample(
            today=today, holidays=holidays, full=full or not has_far,
        )
        sample_dates, near, far = (
            sample.all_dates, sample.near_week, sample.far_week,
        )

    run = SyncRun.objects.create(
        island=island,
        kind=SyncRun.KIND_SCHEDULES,
        sampled_dates=[day.isoformat() for day in sample_dates],
    )
    client = AzoresbusClient(max_requests=max_requests) if max_requests \
        else AzoresbusClient()

    try:
        payloads = _fetch_all(client, sample_dates, run=run)
    except AzoresbusError as exc:
        # Pick up whatever the last in-flight checkpoint wrote before falling
        # over, or the failure save below would blank it back to {} -- wiping
        # out exactly the "how far did it get" answer at the moment it matters.
        run.refresh_from_db(fields=['stats'])
        run.status = SyncRun.STATUS_PARTIAL
        run.error = str(exc)
        run.request_count = client.request_count
        run.finished_at = timezone.now()
        run.save()
        raise SyncAborted(
            f'{exc} — run marked partial after {client.request_count} '
            'requests. Nothing was retired.'
        ) from exc

    report = import_schedules(
        island, run=run, holidays=holidays,
        sampled_dates=sample_dates, **payloads,
    )

    previous = (
        SyncRun.objects.filter(
            island=island, kind=SyncRun.KIND_SCHEDULES,
            status=SyncRun.STATUS_COMPLETED,
        )
        .exclude(pk=run.pk)
        .order_by('-started_at')
        .first()
    )
    decision = evaluate_retirement(
        status=SyncRun.STATUS_COMPLETED,
        journey_count=report['journey_count'],
        previous_journey_count=(
            (previous.stats or {}).get('journey_count') if previous else None
        ),
        sampled_dates=near,
        far_season_dates=far,
    )
    if no_prune:
        decision.allowed = False
        decision.reason = 'suppressed by --no-prune / explicit dates'

    run.status = SyncRun.STATUS_COMPLETED
    run.request_count = client.request_count
    run.finished_at = timezone.now()
    run.stats = {**report, 'retirement': decision.as_dict()}
    run.save()

    return {'run_id': run.id, 'requests': client.request_count, **report,
            'retirement': decision.as_dict()}


def _checkpoint(run, client, *, phase: str, done: int, total: int) -> None:
    """Make progress visible in the admin WHILE the run is still going.

    A single-field update, not run.save(): the caller's in-memory `run` still
    has its other fields set later (status, stats, ...) and must not be
    clobbered by a stale re-save here. This is the fix for a real incident: a
    run sat at request_count=0 for its entire ~13 minute duration because that
    field was previously written only once, at the very end -- indistinguishable
    from a worker that died mid-run and will never finish at all.
    """
    if run is None:
        return
    from azoresbus.models import SyncRun

    SyncRun.objects.filter(pk=run.pk).update(
        request_count=client.request_count,
        stats={'phase': phase, 'phase_progress': f'{done}/{total}'},
    )


def _fetch_all(client, dates, *, run=None) -> dict:
    """Index, route details, per-date listings, then journey details.

    The detail fetches are unavoidable: the listing carries no circulations, so
    a stored hash cannot skip the GET (98 §4 gap). The hash skips the write.

    `run` is optional and purely observational: passing it checkpoints
    progress into SyncRun as the fetch proceeds, so `admin/azoresbus/syncrun/`
    shows live movement instead of a frozen 0 until the run finishes or dies.
    """
    stops = client.get_json('/stops')
    routes = client.get_json('/routes?active=true&passengerInfo=true')
    _checkpoint(run, client, phase='routes', done=1, total=1)

    journeys: dict = {}
    seen: dict[str, str] = {}
    for route_index, route in enumerate(routes, start=1):
        route_id = str(route['id'])
        for day in dates:
            rows = client.get_json(
                f'/routes/{route_id}/journeys?day={day.isoformat()}'
            )
            journeys[(route_id, day)] = rows
            for row in rows:
                seen[str(row['id'])] = route_id
        _checkpoint(run, client, phase='listings',
                   done=route_index, total=len(routes))

    details = {}
    detail_items = list(seen.items())
    for detail_index, (journey_id, route_id) in enumerate(detail_items, start=1):
        details[journey_id] = client.get_json(
            f'/routes/{route_id}/journeys/{journey_id}'
        )
        # Details can number over a thousand; checkpoint every 25 rather than
        # every single one, so this is not itself a source of DB load.
        if detail_index % 25 == 0 or detail_index == len(detail_items):
            _checkpoint(run, client, phase='details',
                       done=detail_index, total=len(detail_items))

    return {'stops': stops, 'routes': routes,
            'journeys': journeys, 'details': details}


# -- orphan recovery --------------------------------------------------------

# Beyond this, a Running row cannot belong to a live worker: the sync lock's
# own TTL has expired by then, so something else could already have started.
STALE_RUN_MINUTES = 45


def reclaim_stale_runs(island, *, all_running: bool = False) -> int:
    """Resolve SyncRun rows whose worker died, and free the lock they held.

    `finally: release_sync_lock()` does not run when a worker is SIGKILLed --
    which is exactly what a redeploy does. The lock then survives its full
    45-minute TTL and every later trigger (deploy bootstrap, beat, the
    staleness backstop) gets "another sync holds the lock" and silently does
    nothing, while the abandoned row sits at Running forever. A redeploy during
    a sync therefore disabled syncing for 45 minutes and looked healthy doing it.

    `all_running=True` is for the deploy path: every worker has just restarted,
    so nothing can legitimately still be running. Everywhere else uses the age
    cutoff, so a sync genuinely in flight is never killed.
    """
    from django.utils import timezone

    from azoresbus.models import SyncRun
    from azoresbus.tasks import release_sync_lock

    stale = SyncRun.objects.filter(
        island=island,
        kind=SyncRun.KIND_SCHEDULES,
        status=SyncRun.STATUS_RUNNING,
    )
    if not all_running:
        cutoff = timezone.now() - timedelta(minutes=STALE_RUN_MINUTES)
        stale = stale.filter(started_at__lt=cutoff)

    reclaimed = stale.count()
    if not reclaimed:
        # Do not touch the lock: it may belong to a run that is genuinely alive.
        return 0

    stale.update(
        status=SyncRun.STATUS_PARTIAL,
        finished_at=timezone.now(),
        error=(
            'Orphaned: no worker was alive to finish this run (most likely a '
            'redeploy or crash mid-sync). Marked partial by reclaim; nothing '
            'was retired.'
        ),
    )
    # The dead run's lock would otherwise block every sync until its TTL.
    release_sync_lock()
    return reclaimed
