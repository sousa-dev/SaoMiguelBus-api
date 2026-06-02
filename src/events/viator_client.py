"""Viator Partner API HTTP client (affiliate / basic-access)."""

from __future__ import annotations

import logging
from typing import Any

import requests
from decouple import config
from django.core.cache import cache

logger = logging.getLogger(__name__)

VIATOR_BASE_URL = config('VIATOR_BASE_URL', default='https://api.viator.com/partner').rstrip('/')
VIATOR_API_KEY = config('VIATOR_API_KEY', default='').strip()
VIATOR_PARTNER_ID = config('VIATOR_PARTNER_ID', default='P00222801')
VIATOR_CAMPAIGN = config('VIATOR_CAMPAIGN', default='sao-miguel-tours')
VIATOR_DESTINATION_ID = config('VIATOR_DESTINATION_ID', default='').strip()
VIATOR_TIMEOUT = config('VIATOR_TIMEOUT', default=25, cast=int)

DESTINATIONS_CACHE_KEY = 'events:viator:destinations'
DESTINATIONS_CACHE_TTL = 86400  # 24h — destination list changes rarely


class ViatorError(Exception):
    """Viator Partner API failure or misconfiguration."""


class ViatorNotConfigured(ViatorError):
    pass


def _require_key() -> str:
    if not VIATOR_API_KEY:
        raise ViatorNotConfigured('VIATOR_API_KEY is not configured')
    return VIATOR_API_KEY


def _headers(locale: str) -> dict[str, str]:
    lang = locale.replace('_', '-')
    if len(lang) == 2:
        lang = f'{lang}-{lang.upper()}'
    return {
        'exp-api-key': _require_key(),
        'Accept': 'application/json;version=2.0',
        'Content-Type': 'application/json',
        'Accept-Language': lang,
    }


def _request(
    method: str,
    path: str,
    *,
    locale: str = 'en',
    params: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f'{VIATOR_BASE_URL}{path}'
    try:
        response = requests.request(
            method,
            url,
            headers=_headers(locale),
            params=params,
            json=json_body,
            timeout=VIATOR_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.exception('Viator request failed: %s %s', method, path)
        raise ViatorError(str(exc)) from exc

    if not response.ok:
        logger.warning(
            'Viator HTTP %s %s: %s',
            response.status_code,
            path,
            response.text[:500],
        )
        raise ViatorError(f'Viator HTTP {response.status_code}')

    try:
        return response.json()
    except ValueError as exc:
        raise ViatorError('Invalid JSON from Viator') from exc


def list_destinations(*, locale: str = 'en') -> list[dict[str, Any]]:
    cached = cache.get(DESTINATIONS_CACHE_KEY)
    if cached is not None:
        return cached

    payload = _request('GET', '/destinations', locale=locale)
    destinations = payload.get('destinations') or []
    cache.set(DESTINATIONS_CACHE_KEY, destinations, DESTINATIONS_CACHE_TTL)
    return destinations


def resolve_destination_id(*, locale: str = 'en') -> str:
    if VIATOR_DESTINATION_ID:
        return VIATOR_DESTINATION_ID

    needles = ('sao miguel', 'são miguel', 'azores', 'açores', 'acores')
    for dest in list_destinations(locale=locale):
        name = (dest.get('name') or '').lower()
        if any(n in name for n in needles):
            dest_id = dest.get('destinationId') or dest.get('ref') or dest.get('id')
            if dest_id is not None:
                return str(dest_id)

    raise ViatorError('Could not resolve São Miguel destination id; set VIATOR_DESTINATION_ID')


def search_products(
    *,
    destination_id: str,
    locale: str = 'en',
    currency: str = 'EUR',
    sort: str = 'DEFAULT',
    start: int = 1,
    count: int = 30,
) -> dict[str, Any]:
    count = min(max(count, 1), 50)
    start = max(start, 1)
    body = {
        'filtering': {'destination': str(destination_id)},
        'sorting': {'sort': sort, 'order': 'DESCENDING'},
        'pagination': {'start': start, 'count': count},
        'currency': currency,
    }
    params = {}
    if VIATOR_CAMPAIGN:
        params['campaign'] = VIATOR_CAMPAIGN
    return _request(
        'POST',
        '/products/search',
        locale=locale,
        params=params or None,
        json_body=body,
    )


def get_product(
    *,
    product_code: str,
    locale: str = 'en',
    currency: str = 'EUR',
) -> dict[str, Any]:
    params: dict[str, str] = {'currency': currency}
    if VIATOR_CAMPAIGN:
        params['campaign'] = VIATOR_CAMPAIGN
    return _request(
        'GET',
        f'/products/{product_code}',
        locale=locale,
        params=params,
    )
