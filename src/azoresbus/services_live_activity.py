"""Registering iOS Live Activity push tokens for tracked trips.

A Live Activity cannot poll while the app is suspended, so it depends on the
server pushing it fresh content over APNs. This is the write side of that:
a rider's device tells us its push-to-update token and which trip(s) it is
tracking; `azoresbus.push_live_activities` (see `tasks.py`) reads these rows
and does the pushing (`apns.py`).

Stores no personal data -- a push token, trip ids and times, nothing that
identifies a person.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.utils import timezone

from azoresbus.models import LiveActivityRegistration
from azoresbus.services_tracking import TrackingDisabled, tracking_enabled

MAX_LEGS = 5


class LiveActivityValidationError(Exception):
    """The request body was malformed -- a 400, not a 500."""


def _parse_datetime(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise LiveActivityValidationError(f'{field} must be an ISO datetime string')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise LiveActivityValidationError(f'{field} is not a valid datetime: {value!r}') from exc
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)


def _parse_legs(raw: Any) -> list[dict]:
    if not isinstance(raw, list) or not raw:
        raise LiveActivityValidationError('legs must be a non-empty list')
    if len(raw) > MAX_LEGS:
        raise LiveActivityValidationError(f'too many legs (max {MAX_LEGS})')

    legs: list[dict] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise LiveActivityValidationError('each leg must be an object')
        trip_id = entry.get('tripId')
        if not isinstance(trip_id, int) or isinstance(trip_id, bool):
            raise LiveActivityValidationError('leg.tripId must be an integer')
        starts_at = _parse_datetime(entry.get('startsAt'), field='leg.startsAt')
        ends_at = _parse_datetime(entry.get('endsAt'), field='leg.endsAt')
        legs.append({
            'tripId': trip_id,
            'startsAt': starts_at.isoformat(),
            'endsAt': ends_at.isoformat(),
        })
    return legs


def register_live_activity(island, data: dict) -> LiveActivityRegistration:
    """Create or refresh a registration. Re-registering the same push token
    (an app relaunch, a language change re-sending templates) updates the
    existing row rather than accumulating duplicates."""
    if not tracking_enabled(island):
        raise TrackingDisabled('tracking_disabled')

    push_token = data.get('pushToken')
    if not isinstance(push_token, str) or not push_token.strip():
        raise LiveActivityValidationError('pushToken is required')

    environment = data.get('environment')
    valid_environments = {
        LiveActivityRegistration.ENVIRONMENT_DEVELOPMENT,
        LiveActivityRegistration.ENVIRONMENT_PRODUCTION,
    }
    if environment not in valid_environments:
        raise LiveActivityValidationError('environment must be "development" or "production"')

    legs = _parse_legs(data.get('legs'))
    expires_at = _parse_datetime(data.get('expiresAt'), field='expiresAt')
    activity_key = str(data.get('activityKey') or '')

    registration, _created = LiveActivityRegistration.objects.update_or_create(
        push_token=push_token.strip(),
        defaults={
            'island': island,
            'environment': environment,
            'activity_key': activity_key,
            'legs': legs,
            'expires_at': expires_at,
            'ended_at': None,
            'failure_count': 0,
        },
    )
    return registration


def unregister_live_activity(island, push_token: str) -> None:
    """Marks the registration ended rather than deleting it -- the beat task
    still owes the Live Activity a final `event: "end"` push. Idempotent: an
    unknown or already-ended token is not an error, matching `disarmTrack`'s
    "turning something off always works" rule elsewhere in this codebase."""
    if not tracking_enabled(island):
        raise TrackingDisabled('tracking_disabled')

    LiveActivityRegistration.objects.filter(
        island=island, push_token=push_token, ended_at__isnull=True,
    ).update(ended_at=timezone.now())
