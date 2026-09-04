"""Core logic for the `azoresbus.push_live_activities` beat task.

Split out of `tasks.py` so trip-selection and snapshot-building are
importable and unit-testable without Celery's task machinery -- the same
split `services_sync.py` makes from `tasks.py` for the schedule sync.

Two small pieces of logic are duplicated here by necessity, not by choice:
which leg is current, and how a `/trips/live` row becomes a snapshot. They
also exist in `features/transit/lib/live-trip-legs.ts` /
`live-trip-state.ts` (TypeScript) and in the Android module's
`LiveTripPoller.kt` (Kotlin) -- three implementations of one rule, kept in
step by hand because Python, TypeScript and Kotlin cannot share code here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

END_GRACE_SECONDS = 5 * 60


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


def current_leg(legs: list[dict[str, Any]], now: datetime) -> dict[str, Any] | None:
    """The leg being ridden, else the one about to be boarded, else the last."""
    if not legs:
        return None
    for leg in legs:
        if now <= _parse(leg['endsAt']):
            return leg
    return legs[-1]


def has_finished(legs: list[dict[str, Any]], now: datetime, *, grace_seconds: int = END_GRACE_SECONDS) -> bool:
    """True once the itinerary's last leg ended more than `grace_seconds` ago."""
    if not legs:
        return True
    return (now - _parse(legs[-1]['endsAt'])).total_seconds() > grace_seconds


def snapshot_from_live_row(
    leg: dict[str, Any],
    row: dict[str, Any] | None,
    now: datetime,
) -> dict[str, Any]:
    """Mirrors `liveTripSnapshotFrom` in `features/transit/lib/live-trip-state.ts`."""
    starts_at = _parse(leg['startsAt'])
    ends_at = _parse(leg['endsAt'])
    span_seconds = (ends_at - starts_at).total_seconds()

    if now < starts_at:
        phase = 'waiting'
    elif now > ends_at:
        phase = 'completed'
    else:
        phase = 'riding'

    if phase == 'completed':
        progress = 1.0
    elif phase == 'waiting' or span_seconds <= 0:
        progress = 0.0
    else:
        progress = max(0.0, min(1.0, (now - starts_at).total_seconds() / span_seconds))

    vehicle = row.get('vehicle') if row and row.get('state') == 'live' else None
    stale = bool(vehicle.get('stale')) if vehicle else False
    # A stale reading is a real position with an unknown ETA -- the server
    # sends an empty `upcomingStops` for it, so there is nothing honest to
    # count down from.
    trusted = vehicle if vehicle and not stale else None
    next_stop = trusted.get('nextStop') if trusted else None
    minutes_to_next_stop = next_stop.get('dueInMinutes') if next_stop else None

    state = phase
    if phase == 'riding' and stale:
        state = 'stale'
    elif phase == 'riding' and minutes_to_next_stop is not None and minutes_to_next_stop <= 1:
        state = 'arriving'

    # Delay lives on the fleet list, not the detail, so it survives even when
    # the detail read that would give a stop ETA failed (the "stale" case).
    delay_seconds = vehicle.get('delaySeconds') if vehicle else None
    delay_minutes = round(delay_seconds / 60) if isinstance(delay_seconds, (int, float)) else None

    return {
        'v': 1,
        'state': state,
        'nextStopName': next_stop.get('name') if next_stop else None,
        'minutesToNextStop': minutes_to_next_stop,
        'delayMinutes': delay_minutes,
        'progress': progress,
        'updatedAtEpochMs': now.timestamp() * 1000,
    }
