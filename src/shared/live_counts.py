"""Cross-operator "how many buses are live right now" cache.

Fed as a side effect of a REAL vendor fleet fetch -- the live map's polling of
`/vehicles`, or a health probe that touches the vendor -- never by the hub
screens themselves. One rider's live map keeps this warm for every hub visitor
on the island; a hub that only reads this module never talks to the AVL vendor.

Two keys per operator per island:

    live:count:{operator}:{island_key}           the record itself
    live:count:attempt:{operator}:{island_key}   a 5-minute "we just tried" marker

The record's own TTL matters less than `read_live_count`'s own age check: an
envelope surviving in Redis a little past its logical TTL (GC lag, a clock
skew) must still read back as gone, not as a small integer overflow into
staleness. So the cache TTL is kept generous and the real expiry is enforced by
comparing `recordedAt` to `get_live_count_ttl()` on read.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from decouple import config
from django.core.cache import cache
from django.utils import timezone

from shared.tracking_cache import clamp
from transit.services.schedule_phase import now_in_azores

OPERATOR_AZORESBUS = 'azoresbus'
OPERATOR_MINIBUS = 'minibus'

STATUS_OK = 'ok'
STATUS_UNAVAILABLE = 'unavailable'

RECORD_TTL_DEFAULT = 1800
RECORD_TTL_MIN = 60
RECORD_TTL_MAX = 6 * 3600

# How long one "let's try the vendor" attempt blocks the next one, regardless
# of whether it succeeded -- the whole point is at most one call per operator
# per window, not one successful call per window.
ATTEMPT_TTL = 300

# 06:00 <= hour < 19:00 in Atlantic/Azores. Outside this window a cold/zero
# record is simply served as-is; nothing wakes the vendor at 3am for a hub
# nobody is looking at.
DAYTIME_START_HOUR = 6
DAYTIME_END_HOUR = 19


def get_live_count_ttl() -> int:
    return clamp(
        config('LIVE_COUNT_TTL', default=RECORD_TTL_DEFAULT, cast=int),
        RECORD_TTL_MIN, RECORD_TTL_MAX,
    )


def count_key(operator: str, island_key: str) -> str:
    return f'live:count:{operator}:{island_key}'


def attempt_key(operator: str, island_key: str) -> str:
    return f'live:count:attempt:{operator}:{island_key}'


def record_live_count(operator: str, island_key: str, count: int, *, fetched_at: datetime) -> None:
    """Record a real fleet size, timestamped with the ACTUAL fetch time.

    `fetched_at` is the fleet cache's own `CacheMeta.cached_at`, not
    `timezone.now()`: re-recording on a cache hit (same underlying fetch) must
    not make the record look fresher than the fleet snapshot behind it.
    """
    envelope = {'status': STATUS_OK, 'vehicles': int(count), 'recordedAt': fetched_at.isoformat()}
    cache.set(count_key(operator, island_key), envelope, get_live_count_ttl())


def record_live_outage(operator: str, island_key: str) -> None:
    envelope = {'status': STATUS_UNAVAILABLE, 'vehicles': None, 'recordedAt': timezone.now().isoformat()}
    cache.set(count_key(operator, island_key), envelope, get_live_count_ttl())


def read_live_count(operator: str, island_key: str) -> dict[str, Any] | None:
    envelope = cache.get(count_key(operator, island_key))
    if envelope is None:
        return None
    recorded_at = datetime.fromisoformat(envelope['recordedAt'])
    age = (timezone.now() - recorded_at).total_seconds()
    if age > get_live_count_ttl():
        return None
    return envelope


def mark_refresh_attempt(operator: str, island_key: str) -> bool:
    """True exactly once per `ATTEMPT_TTL` window: this caller owns the refresh."""
    return cache.add(attempt_key(operator, island_key), '1', ATTEMPT_TTL)


def is_refresh_daytime(now: datetime | None = None) -> bool:
    hour = (now or now_in_azores()).hour
    return DAYTIME_START_HOUR <= hour < DAYTIME_END_HOUR


def needs_refresh(record: dict[str, Any] | None) -> bool:
    """No record, or the record itself has nothing worth showing."""
    if record is None:
        return True
    if record['status'] == STATUS_UNAVAILABLE:
        return True
    return record['status'] == STATUS_OK and record['vehicles'] == 0


def should_attempt_refresh(record: dict[str, Any] | None, *, now: datetime | None = None) -> bool:
    """The daytime rule, with one exception: total silence never waits for
    morning.

    A record that is merely empty or outaged (`needs_refresh` but not `None`)
    only tops up 06:00-18:59 -- there is something to show either way, so a
    3am blip can just sit until service hours. A completely missing record
    means the cache has NOTHING for this operator at all (first deploy, a
    Redis flush, a brand-new operator) -- and unlike AzoresBus, MiniBus has no
    background sweep keeping it warm on its own, so waiting for daytime could
    mean an all-night blank hub for no reason. Still gated by
    `mark_refresh_attempt`'s 5-minute window either way, so this never means
    more than one extra call per operator per window.
    """
    if record is None:
        return True
    return needs_refresh(record) and is_refresh_daytime(now)


__all__ = [
    'ATTEMPT_TTL',
    'DAYTIME_END_HOUR',
    'DAYTIME_START_HOUR',
    'OPERATOR_AZORESBUS',
    'OPERATOR_MINIBUS',
    'STATUS_OK',
    'STATUS_UNAVAILABLE',
    'attempt_key',
    'count_key',
    'get_live_count_ttl',
    'is_refresh_daytime',
    'mark_refresh_attempt',
    'needs_refresh',
    'read_live_count',
    'record_live_count',
    'record_live_outage',
    'should_attempt_refresh',
]
