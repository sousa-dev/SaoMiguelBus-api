"""Fare tables from azoresbus.pt, stored verbatim and served flattened.

Storage stays schemaless on purpose (02 §6): all 148 `fareUnits` values are
human-readable band labels, and the category/group/tariff nesting is the
operator's editorial structure, which will change without warning. Parsing that
into relational tables buys nothing and breaks on the first restructure.

`fareUnitType: "km"` is NOT a price calculator. Nothing in /api/stops, the
journeys or this file gives kilometres between two stops, so this module renders
the operator's tables and never computes a fare. No caller should present one
(98 §4 gap "Fare distance").

The proxy matters here for a different reason than schedules: azoresbus.pt sends
no Access-Control-Allow-Origin, so a browser cannot fetch it directly.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone as dt_timezone
from email.utils import parsedate_to_datetime

import requests
from decouple import config

from azoresbus.models import TariffSnapshot
from shared.upstream_proxy import build_request, split_origin

logger = logging.getLogger(__name__)

TARIFFS_URL = config(
    'AZORESBUS_TARIFFS_URL',
    default='https://azoresbus.pt/static/json/tariffs.json',
)
TARIFFS_TIMEOUT = config('AZORESBUS_TARIFFS_TIMEOUT', default=20, cast=int)

USER_AGENT = (
    'SaoMiguelBus/3.x tariffs-sync '
    '(+https://saomiguelbus.com; contact@saomiguelbus.com)'
)


class TariffsError(Exception):
    """Tariffs fetch failed."""


def content_hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode('utf-8')
    ).hexdigest()


def _parse_http_date(raw: str | None):
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None


def _parse_date(raw):
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw)[:10], '%Y-%m-%d').date()
    except ValueError:
        return None


def current_snapshot(island) -> TariffSnapshot | None:
    return TariffSnapshot.objects.filter(island=island, is_current=True).first()


def store_snapshot(island, *, payload: dict, headers, source_url: str):
    """Append-only: one row per distinct content hash.

    Fare history for free, and it lets the app show "prices updated on X".
    """
    digest = content_hash(payload)

    existing = TariffSnapshot.objects.filter(
        island=island, content_hash=digest,
    ).first()
    if existing is not None:
        return existing

    TariffSnapshot.objects.filter(island=island, is_current=True).update(
        is_current=False,
    )
    return TariffSnapshot.objects.create(
        island=island,
        source_url=source_url,
        effective_date=_parse_date(payload.get('date')),
        upstream_etag=(headers or {}).get('ETag', '') or '',
        upstream_modified_at=_parse_http_date((headers or {}).get('Last-Modified')),
        payload=payload,
        content_hash=digest,
        is_current=True,
    )


def sync_tariffs(island) -> dict:
    """Conditional GET. Costs nothing when the fares have not moved."""
    previous = current_snapshot(island)
    request_headers = {'User-Agent': USER_AGENT, 'Accept': 'application/json'}
    if previous and previous.upstream_etag:
        request_headers['If-None-Match'] = previous.upstream_etag

    # Through the Pi when one is configured. azoresbus.pt is a DIFFERENT host
    # from azb.elevensystems.pt and whether it blocks our datacenter egress is
    # untested, so it takes the same route rather than finding out in
    # production.
    origin, path = split_origin(TARIFFS_URL)
    url, proxy_headers = build_request(origin, path)
    request_headers.update(proxy_headers)

    try:
        response = requests.get(
            url, timeout=TARIFFS_TIMEOUT, headers=request_headers,
        )
    except requests.RequestException as exc:
        logger.exception('tariffs fetch failed')
        raise TariffsError(str(exc)) from exc

    if response.status_code == 304:
        return {'changed': False, 'reason': 'not modified'}

    if not response.ok:
        raise TariffsError(f'HTTP {response.status_code} from {TARIFFS_URL}')

    try:
        payload = response.json()
    except ValueError as exc:
        raise TariffsError('invalid JSON from tariffs.json') from exc

    snapshot = store_snapshot(
        island, payload=payload, headers=response.headers,
        source_url=TARIFFS_URL,
    )
    changed = snapshot.content_hash != (previous.content_hash if previous else None)
    return {'changed': changed, 'snapshot_id': snapshot.id}


def serialize_tariffs(snapshot: TariffSnapshot) -> dict:
    """Flatten the redundant `groups` level, keep every value verbatim."""
    payload = snapshot.payload or {}
    today = datetime.now(dt_timezone.utc).date()

    categories = []
    for category in payload.get('categories') or []:
        tariffs = []
        # Every category has exactly one group today, but merge rather than
        # assume index 0 (02 §6).
        for group in category.get('groups') or []:
            for tariff in group.get('tariffs') or []:
                tariffs.append({
                    'name': tariff.get('name', ''),
                    'note': tariff.get('comment', '') or '',
                    'fareUnitType': tariff.get('fareUnitType'),
                    'prices': [
                        {
                            # A LABEL, never parsed into a numeric range.
                            'band': price.get('fareUnits'),
                            'price': price.get('price'),
                        }
                        for price in tariff.get('prices') or []
                    ],
                })
        categories.append({'name': category.get('name', ''), 'tariffs': tariffs})

    effective = snapshot.effective_date
    return {
        'effectiveDate': effective.isoformat() if effective else None,
        'lastUpdatedAt': (
            snapshot.upstream_modified_at.isoformat()
            if snapshot.upstream_modified_at else None
        ),
        'fetchedAt': snapshot.fetched_at.isoformat(),
        'isFuture': bool(effective and effective > today),
        'notes': payload.get('comment', '') or '',
        'infos': payload.get('infos') or [],
        'categories': categories,
    }
