"""Short-TTL cache with stale-grace fallback for upstream AVL proxies.

Extracted verbatim from `minibus/services_tracking.py`, which grew it first. The
only generalisation is `error_type`: minibus caught `MinibusTrackingError`
directly, so a second operator could not reuse it without either catching the
wrong exception or copying the file. Copying it is what this module exists to
prevent — AzoresBus is the second caller, and there will be a third.

The shape it enforces, which is the whole point:

    fresh envelope        -> serve it, `hit`
    expired envelope      -> refresh under a lock, `miss`
    refresh failed        -> serve the expired envelope while it is inside the
                             stale grace, `stale`; re-raise once it is not

A brief upstream blip therefore does not blank a map that was working a second
ago, and a thundering herd of pollers produces one upstream call rather than N.
"""

from __future__ import annotations

import time as _time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from django.core.cache import cache
from django.utils import timezone

LOCK_POLL_ATTEMPTS = 30
LOCK_POLL_INTERVAL = 0.1


@dataclass(frozen=True)
class CacheMeta:
    cached_at: datetime
    cache_status: str  # hit | miss | stale
    stale: bool = False


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(value, high))


def cached_fetch(
    *,
    cache_key: str,
    lock_key: str,
    fetch_fn: Callable[[], Any],
    cache_ttl: int,
    stale_grace: int,
    lock_ttl: int,
    error_type: type[Exception],
) -> tuple[Any, CacheMeta]:
    envelope = cache.get(cache_key)
    now = timezone.now()

    if envelope is not None:
        fetched_at = parse_fetched_at(envelope['fetched_at'])
        age = (now - fetched_at).total_seconds()
        if age <= cache_ttl:
            return envelope['payload'], CacheMeta(
                cached_at=fetched_at,
                cache_status='hit',
                stale=False,
            )

    try:
        payload, fetched_at, cache_status = _refresh_with_lock(
            cache_key=cache_key,
            lock_key=lock_key,
            fetch_fn=fetch_fn,
            cache_ttl=cache_ttl,
            stale_grace=stale_grace,
            lock_ttl=lock_ttl,
        )
        return payload, CacheMeta(cached_at=fetched_at, cache_status=cache_status, stale=False)
    except error_type:
        if envelope is None:
            raise
        fetched_at = parse_fetched_at(envelope['fetched_at'])
        age = (now - fetched_at).total_seconds()
        if age <= stale_grace:
            return envelope['payload'], CacheMeta(
                cached_at=fetched_at,
                cache_status='stale',
                stale=True,
            )
        raise


def _refresh_with_lock(
    *,
    cache_key: str,
    lock_key: str,
    fetch_fn: Callable[[], Any],
    cache_ttl: int,
    stale_grace: int,
    lock_ttl: int,
) -> tuple[Any, datetime, str]:
    if cache.add(lock_key, '1', lock_ttl):
        try:
            payload = fetch_fn()
            fetched_at = timezone.now()
            envelope = {'payload': payload, 'fetched_at': fetched_at.isoformat()}
            cache.set(cache_key, envelope, cache_ttl + stale_grace)
            return payload, fetched_at, 'miss'
        finally:
            cache.delete(lock_key)

    for _ in range(LOCK_POLL_ATTEMPTS):
        _time.sleep(LOCK_POLL_INTERVAL)
        envelope = cache.get(cache_key)
        if envelope is not None:
            fetched_at = parse_fetched_at(envelope['fetched_at'])
            return envelope['payload'], fetched_at, 'miss'

    payload = fetch_fn()
    fetched_at = timezone.now()
    envelope = {'payload': payload, 'fetched_at': fetched_at.isoformat()}
    cache.set(cache_key, envelope, cache_ttl + stale_grace)
    return payload, fetched_at, 'miss'


def parse_fetched_at(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed
