"""Tours listing via Viator Partner API (cached proxy)."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from decouple import config
from django.core.cache import cache

from events.viator_client import (
    ViatorError,
    ViatorNotConfigured,
    get_product,
    resolve_destination_id,
    search_products,
)

logger = logging.getLogger(__name__)

CACHE_TTL = 3600  # Viator allows caching search results up to 1 hour


def _affiliate_url(url: str | None) -> str:
    if not url:
        return ''
    try:
        parsed = urlparse(url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        partner_id = config('VIATOR_PARTNER_ID', default='P00222801')
        campaign = config('VIATOR_CAMPAIGN', default='sao-miguel-tours')
        query.setdefault('pid', partner_id)
        if campaign:
            query.setdefault('campaign', campaign)
        query.setdefault('medium', 'link')
        new_query = urlencode(query)
        return urlunparse(parsed._replace(query=new_query))
    except Exception:
        return url


def _best_image_url(images: list[dict[str, Any]] | None) -> str:
    if not images:
        return ''
    cover = next((img for img in images if img.get('isCover')), images[0])
    variants = cover.get('variants') or []
    best = ''
    best_area = 0
    for variant in variants:
        url = (variant.get('url') or '').strip()
        if not url:
            continue
        w = variant.get('width') or 0
        h = variant.get('height') or 0
        area = w * h
        if area >= best_area:
            best_area = area
            best = url
    return best


def _duration_minutes(product: dict[str, Any]) -> int | None:
    duration = product.get('duration') or {}
    fixed = duration.get('fixedDurationInMinutes')
    if fixed is not None:
        return int(fixed)
    variable = duration.get('variableDurationFromMinutes')
    if variable is not None:
        return int(variable)
    unstructured = duration.get('unstructuredDuration')
    if unstructured:
        return None
    return None


def _from_price(product: dict[str, Any]) -> tuple[float | None, str]:
    pricing = product.get('pricing') or {}
    summary = pricing.get('summary') or {}
    from_price = summary.get('fromPrice')
    if from_price is None:
        from_price = pricing.get('fromPrice')
    currency = pricing.get('currency') or product.get('currency') or 'EUR'
    if from_price is None:
        return None, currency
    try:
        return float(from_price), currency
    except (TypeError, ValueError):
        return None, currency


def _reviews(product: dict[str, Any]) -> tuple[float | None, int | None]:
    reviews = product.get('reviews') or {}
    rating = reviews.get('combinedAverageRating')
    total = reviews.get('totalReviews')
    try:
        rating_f = float(rating) if rating is not None else None
    except (TypeError, ValueError):
        rating_f = None
    try:
        total_i = int(total) if total is not None else None
    except (TypeError, ValueError):
        total_i = None
    return rating_f, total_i


def _serialize_images(images: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    if not images:
        return []
    out: list[dict[str, str]] = []
    for img in images:
        url = _best_image_url([img])
        if url:
            out.append({'url': url, 'caption': (img.get('caption') or '').strip()})
    return out


def serialize_tour_summary(product: dict[str, Any]) -> dict[str, Any]:
    code = product.get('productCode') or ''
    from_price, currency = _from_price(product)
    rating, review_count = _reviews(product)
    thumbnail = _best_image_url(product.get('images'))
    booking_url = _affiliate_url(product.get('productUrl'))

    return {
        'code': code,
        'title': (product.get('title') or '').strip(),
        'thumbnailUrl': thumbnail,
        'rating': rating,
        'reviewCount': review_count,
        'fromPrice': from_price,
        'currency': currency,
        'durationMinutes': _duration_minutes(product),
        'bookingUrl': booking_url,
    }


def serialize_tour_detail(product: dict[str, Any]) -> dict[str, Any]:
    summary = serialize_tour_summary(product)
    flags = product.get('flags') or []
    if isinstance(flags, list):
        flag_list = [str(f) for f in flags]
    else:
        flag_list = []

    description = (product.get('description') or product.get('shortDescription') or '').strip()
    hero = _best_image_url(product.get('images'))

    return {
        **summary,
        'heroUrl': hero or summary.get('thumbnailUrl') or '',
        'description': description,
        'images': _serialize_images(product.get('images')),
        'flags': flag_list,
    }


def _locale_key(locale: str) -> str:
    return locale.split('-')[0].lower() if locale else 'en'


def list_tours(
    *,
    locale: str = 'en',
    currency: str = 'EUR',
    sort: str = 'DEFAULT',
    start: int = 1,
    count: int = 30,
) -> list[dict[str, Any]]:
    loc = _locale_key(locale)
    try:
        dest_id = resolve_destination_id(locale=loc)
    except ViatorNotConfigured:
        raise
    except ViatorError:
        raise

    cache_key = f'events:tours:{dest_id}:{loc}:{currency}:{sort}:{start}:{count}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    payload = search_products(
        destination_id=dest_id,
        locale=loc,
        currency=currency,
        sort=sort,
        start=start,
        count=count,
    )
    products = payload.get('products') or []
    tours = [
        serialize_tour_summary(p)
        for p in products
        if (p.get('status') or 'ACTIVE') == 'ACTIVE' and p.get('productCode')
    ]
    cache.set(cache_key, tours, CACHE_TTL)
    return tours


def get_tour(
    product_code: str,
    *,
    locale: str = 'en',
    currency: str = 'EUR',
) -> dict[str, Any] | None:
    code = (product_code or '').strip()
    if not code:
        return None

    loc = _locale_key(locale)
    cache_key = f'events:tour:{code}:{loc}:{currency}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        product = get_product(product_code=code, locale=loc, currency=currency)
    except ViatorNotConfigured:
        raise
    except ViatorError:
        raise

    if (product.get('status') or 'ACTIVE') != 'ACTIVE':
        return None

    detail = serialize_tour_detail(product)
    cache.set(cache_key, detail, CACHE_TTL)
    return detail
