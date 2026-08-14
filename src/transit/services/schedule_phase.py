"""Which network is active, and when it changes.

The cutover lives on the server, not in the app (00 Decision 1). A build
installed in June gets correct September timetables because it never had the
decision to make: it sends no `dataset`, and the server resolves one.

All date logic runs in Atlantic/Azores. `TIME_ZONE` is UTC globally, so that is
an explicit conversion here rather than a settings change -- and it matters:
Azores is UTC-1 in summer, so comparing in UTC would flip an hour early, exactly
the bug that bites a tourist whose phone is still on Lisbon time.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.utils import timezone

from transit.models import DATASET_AZORESBUS, DATASET_CHOICES, DATASET_LEGACY, Trip


AZORES = ZoneInfo('Atlantic/Azores')
FLAG_NAMESPACE = 'azoresbus'

VALID_DATASETS = {value for value, _ in DATASET_CHOICES}

PHASE_PREVIEW = 'preview'
PHASE_LIVE = 'live'
PHASE_SETTLED = 'settled'


def azoresbus_flags(island) -> dict:
    """The `azoresbus` block of `Island.feature_flags`, editable in admin.

    Every phase decision is one field in here, so a rollback is an edit rather
    than a deploy (00 Rollback).
    """
    flags = getattr(island, 'feature_flags', None) or {}
    block = flags.get(FLAG_NAMESPACE)
    return block if isinstance(block, dict) else {}


def _instant(island, key: str) -> datetime | None:
    raw = azoresbus_flags(island).get(key)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=AZORES)


def cutover_at(island) -> datetime | None:
    """The instant the new network becomes active. None => never."""
    return _instant(island, 'cutoverAt')


def banner_until(island) -> datetime | None:
    return _instant(island, 'bannerUntil')


def now_in_azores() -> datetime:
    return timezone.now().astimezone(AZORES)


def today_in_azores() -> date:
    return now_in_azores().date()


def _has_rows(island, dataset: str) -> bool:
    return Trip.objects.filter(
        island=island, dataset=dataset, source=Trip.SOURCE_OPERATOR,
    ).exists()


def resolve_dataset(
    island,
    *,
    requested: str | None = None,
    on_date: date | None = None,
) -> str:
    """Explicit request wins; otherwise the Azores date decides.

    `requested` is the preview toggle and admin/debug only. It must never be
    populated from a cached bootstrap value, and clients must never send
    `dataset=legacy` on a public URL (98 §4 gap, "Stale bootstrap").

    `on_date` is used when the caller supplied a real date. Every shipped client
    sends a day-type instead, so the common path falls through to the server's
    own Azores date -- which is precisely what makes an un-updated app correct on
    1 September.
    """
    if requested in VALID_DATASETS:
        return requested

    if island is None:
        return DATASET_LEGACY

    cutover = cutover_at(island)
    if cutover is None:
        # No cutover configured: the active network is legacy, forever.
        return DATASET_LEGACY

    if on_date is not None:
        crossed = on_date >= cutover.astimezone(AZORES).date()
    else:
        crossed = now_in_azores() >= cutover.astimezone(AZORES)

    if not crossed:
        return DATASET_LEGACY

    # Safety net: shipping the cutover before a sync has run must not empty the
    # app. This covers "the sync never ran", NOT "the sync ran badly" -- a
    # partially imported network has rows and will not trip it. The procedural
    # guard for that is --dry-run and the per-dataset counts in the sync report.
    if not _has_rows(island, DATASET_AZORESBUS):
        return DATASET_LEGACY

    return DATASET_AZORESBUS


def schedule_phase(island, *, at: datetime | None = None) -> str:
    """preview -> live -> settled, from the same two instants the app renders."""
    moment = (at or timezone.now()).astimezone(AZORES)
    cutover = cutover_at(island)

    if cutover is None or moment < cutover.astimezone(AZORES):
        return PHASE_PREVIEW

    retires = banner_until(island)
    if retires is not None and moment >= retires.astimezone(AZORES):
        return PHASE_SETTLED

    return PHASE_LIVE


def next_transition_at(island) -> datetime | None:
    """When the current phase stops being true.

    Exists because the app persists bootstrap for 24h and `useBootstrapCached`
    never refetches, so without this it has no way to know its copy became a lie
    (98 §4 gap "Stale bootstrap").
    """
    moment = now_in_azores()
    for instant in (cutover_at(island), banner_until(island)):
        if instant is not None and moment < instant.astimezone(AZORES):
            return instant
    return None


__all__ = [
    'AZORES',
    'DATASET_AZORESBUS',
    'DATASET_LEGACY',
    'PHASE_LIVE',
    'PHASE_PREVIEW',
    'PHASE_SETTLED',
    'azoresbus_flags',
    'banner_until',
    'cutover_at',
    'next_transition_at',
    'now_in_azores',
    'resolve_dataset',
    'schedule_phase',
    'today_in_azores',
]
