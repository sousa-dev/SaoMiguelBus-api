"""Marketplace business logic: CRUD, ownership, moderation, rating, search.

Read/write helpers assume the active island is bound (the v3 views wrap calls
in ``with for_island(request.island):`` so ``Model.objects`` auto-filters).
Creates pass ``island`` explicitly. Ownership is pseudonymous, keyed on the
``created_by_session_hash`` produced by ``consent.hash_session_id``.
"""

from __future__ import annotations

import math
import random
from decimal import Decimal
from typing import Any

from django.db.models import Avg, Count, Q
from django.utils.text import slugify

from marketplace.models import Review, ServiceCategory, ServiceProvider
from marketplace.phone import normalize_pt_phone

MAX_LIMIT = 100
DEFAULT_LIMIT = 50
VALID_MODERATE_ACTIONS = {'publish': ServiceProvider.PUBLISHED, 'reject': ServiceProvider.REJECTED}
VALID_SORTS = frozenset({'random', 'rating', 'distance', 'name', 'newest'})
DEFAULT_SORT = 'random'


class MarketplaceError(Exception):
    """Base for marketplace service errors."""


class OwnershipError(MarketplaceError):
    """Raised when a non-owner / non-staff attempts a restricted write."""


class CategoryNotFound(MarketplaceError):
    """Raised when a write references an unknown category slug."""


class InvalidCategoryName(MarketplaceError):
    """Raised when a suggested category name fails validation."""


class InvalidSort(MarketplaceError):
    """Raised when list sort params are invalid."""


class SortDistanceRequiresCoords(MarketplaceError):
    """Raised when sort=distance without lat/lng."""


_CATEGORY_NAME_MIN = 2
_CATEGORY_NAME_MAX = 80


# --------------------------------------------------------------------------- #
# Serialization
# --------------------------------------------------------------------------- #

def serialize_category(category: ServiceCategory) -> dict[str, Any]:
    return {
        'id': category.id,
        'name': category.name,
        'slug': category.slug,
        'icon': category.icon,
        'userSuggested': category.user_suggested,
    }


def serialize_provider(provider: ServiceProvider, *, include_private: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        'id': provider.id,
        'name': provider.name,
        'category': {
            'id': provider.category_id,
            'name': provider.category.name,
            'slug': provider.category.slug,
        },
        'bio': provider.bio,
        'hourlyRate': float(provider.hourly_rate) if provider.hourly_rate is not None else None,
        'phone': provider.phone,
        'whatsapp': provider.whatsapp,
        'email': provider.email,
        'website': provider.website,
        'socials': provider.socials or [],
        'latitude': provider.latitude,
        'longitude': provider.longitude,
        'isPromoted': provider.is_promoted,
        'verifiedByOwner': provider.verified_by_owner,
        'rating': float(provider.rating),
        'reviewCount': provider.review_count,
    }
    if include_private:
        payload['status'] = provider.status
        payload['claimedOwner'] = provider.claimed_owner
        payload['internalEmail'] = provider.internal_email
        payload['internalPhone'] = provider.internal_phone
        payload['verifiedByOwner'] = provider.verified_by_owner
    return payload


def serialize_review(review: Review) -> dict[str, Any]:
    return {
        'id': review.id,
        'providerId': review.provider_id,
        'rating': review.rating,
        'text': review.text,
        'createdAt': review.created_at.isoformat(),
        'status': review.status,
    }


# --------------------------------------------------------------------------- #
# Categories
# --------------------------------------------------------------------------- #

def list_categories() -> list[dict[str, Any]]:
    return [serialize_category(c) for c in ServiceCategory.objects.all()]


def _resolve_category(slug: str) -> ServiceCategory:
    try:
        return ServiceCategory.objects.get(slug=slug)
    except ServiceCategory.DoesNotExist as exc:
        raise CategoryNotFound(slug) from exc


def _normalize_category_name(name: str) -> str:
    cleaned = ' '.join(name.split())
    if len(cleaned) < _CATEGORY_NAME_MIN or len(cleaned) > _CATEGORY_NAME_MAX:
        raise InvalidCategoryName('length')
    if not any(ch.isalpha() for ch in cleaned):
        raise InvalidCategoryName('letters')
    slug = slugify(cleaned)[: _CATEGORY_NAME_MAX]
    if not slug:
        raise InvalidCategoryName('slug')
    return cleaned


def get_or_create_category_by_name(*, island, name: str) -> ServiceCategory:
    """Resolve an existing category or create a user-suggested one."""
    cleaned = _normalize_category_name(name)
    slug = slugify(cleaned)[: _CATEGORY_NAME_MAX]
    existing = ServiceCategory.objects.filter(island=island, slug=slug).first()
    if existing:
        return existing
    existing = ServiceCategory.objects.filter(island=island, name__iexact=cleaned).first()
    if existing:
        return existing
    return ServiceCategory.objects.create(
        island=island,
        name=cleaned,
        slug=slug,
        user_suggested=True,
    )


def _resolve_category_from_write(*, island, data: dict[str, Any]) -> ServiceCategory:
    slug = (data.get('category_slug') or '').strip()
    name = (data.get('category_name') or '').strip()
    if slug and name:
        raise InvalidCategoryName('both')
    if slug:
        return _resolve_category(slug)
    if name:
        return get_or_create_category_by_name(island=island, name=name)
    return _resolve_category('other')


# --------------------------------------------------------------------------- #
# Providers — reads
# --------------------------------------------------------------------------- #

def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lng / 2) ** 2
    )
    return radius * 2 * math.asin(math.sqrt(a))


def _random_tiebreakers(providers: list[ServiceProvider]) -> dict[int, float]:
    return {provider.id: random.random() for provider in providers}


def _provider_distance_km(
    provider: ServiceProvider,
    *,
    lat: float | None,
    lng: float | None,
) -> float:
    if lat is None or lng is None or provider.latitude is None or provider.longitude is None:
        return float('inf')
    return _haversine_km(lat, lng, provider.latitude, provider.longitude)


def _sort_providers_for_listing(
    providers: list[ServiceProvider],
    *,
    sort: str = DEFAULT_SORT,
    lat: float | None = None,
    lng: float | None = None,
) -> list[ServiceProvider]:
    """Order: promoted first, then user-selected sort (default random within tier)."""
    if sort not in VALID_SORTS:
        raise InvalidSort(sort)
    if sort == 'distance' and (lat is None or lng is None):
        raise SortDistanceRequiresCoords()

    tiebreakers = _random_tiebreakers(providers)

    def sort_key(provider: ServiceProvider) -> tuple:
        promoted_rank = 0 if provider.is_promoted else 1
        random_rank = tiebreakers[provider.id]
        if sort == 'random':
            return (promoted_rank, random_rank)
        if sort == 'rating':
            return (promoted_rank, -float(provider.rating), random_rank)
        if sort == 'distance':
            return (promoted_rank, _provider_distance_km(provider, lat=lat, lng=lng), random_rank)
        if sort == 'name':
            return (promoted_rank, provider.name.lower())
        if sort == 'newest':
            return (promoted_rank, -provider.created_at.timestamp())
        raise InvalidSort(sort)

    providers.sort(key=sort_key)
    return providers


def _apply_radius_filter(
    providers: list[ServiceProvider],
    *,
    lat: float | None,
    lng: float | None,
    radius_km: float | None,
) -> list[ServiceProvider]:
    if radius_km is None or lat is None or lng is None:
        return providers
    return [
        provider
        for provider in providers
        if _provider_distance_km(provider, lat=lat, lng=lng) <= radius_km
    ]


def _catalog_review_meta(providers: list[ServiceProvider]) -> dict[str, Any]:
    total = len(providers)
    if total == 0:
        return {'reviewedShare': 0.0, 'reviewedCount': 0, 'totalCount': 0}
    reviewed_count = sum(1 for provider in providers if provider.review_count > 0)
    return {
        'reviewedShare': round(reviewed_count / total, 4),
        'reviewedCount': reviewed_count,
        'totalCount': total,
    }


def list_providers(
    *,
    category: str | None = None,
    q: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    radius_km: float | None = None,
    min_rating: float | None = None,
    has_rate: bool | None = None,
    verified: bool | None = None,
    sort: str = DEFAULT_SORT,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    if sort not in VALID_SORTS:
        raise InvalidSort(sort)
    if sort == 'distance' and (lat is None or lng is None):
        raise SortDistanceRequiresCoords()

    qs = (
        ServiceProvider.objects.select_related('category')
        .filter(status=ServiceProvider.PUBLISHED)
    )
    if category:
        qs = qs.filter(category__slug=category)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(bio__icontains=q))
    if has_rate:
        qs = qs.filter(hourly_rate__isnull=False)
    if verified:
        qs = qs.filter(verified_by_owner=True)

    limit = max(1, min(limit, MAX_LIMIT))
    providers = list(qs)
    providers = _apply_radius_filter(providers, lat=lat, lng=lng, radius_km=radius_km)
    meta = _catalog_review_meta(providers)
    if min_rating is not None:
        providers = [provider for provider in providers if float(provider.rating) >= min_rating]
    providers = _sort_providers_for_listing(providers, sort=sort, lat=lat, lng=lng)
    return {
        'providers': [serialize_provider(provider) for provider in providers[:limit]],
        'meta': meta,
    }


def _get_provider_or_none(provider_id: int) -> ServiceProvider | None:
    try:
        return ServiceProvider.objects.select_related('category').get(id=provider_id)
    except ServiceProvider.DoesNotExist:
        return None


def get_provider(
    provider_id: int,
    *,
    viewer_session_hash: str = '',
    is_staff: bool = False,
) -> dict[str, Any] | None:
    provider = _get_provider_or_none(provider_id)
    if provider is None or provider.status == ServiceProvider.DELETED:
        return None
    if provider.status != ServiceProvider.PUBLISHED:
        if not (is_staff or provider.is_owned_by(viewer_session_hash)):
            return None
    return serialize_provider(provider, include_private=True)


# --------------------------------------------------------------------------- #
# Providers — writes
# --------------------------------------------------------------------------- #

_PROVIDER_WRITE_FIELDS = (
    'name',
    'bio',
    'hourly_rate',
    'phone',
    'whatsapp',
    'email',
    'website',
    'socials',
    'claimed_owner',
    'internal_email',
    'internal_phone',
    'latitude',
    'longitude',
)


def _apply_provider_fields(provider: ServiceProvider, data: dict[str, Any]) -> None:
    slug = (data.get('category_slug') or '').strip() if 'category_slug' in data else ''
    name = (data.get('category_name') or '').strip() if 'category_name' in data else ''
    if slug or name:
        provider.category = _resolve_category_from_write(
            island=provider.island,
            data={'category_slug': slug, 'category_name': name},
        )
    for field in _PROVIDER_WRITE_FIELDS:
        if field in data:
            setattr(provider, field, data[field])


def create_provider(*, island, session_hash: str, data: dict[str, Any]) -> dict[str, Any]:
    category = _resolve_category_from_write(island=island, data=data)
    provider = ServiceProvider(
        island=island,
        category=category,
        created_by_session_hash=session_hash,
        status=ServiceProvider.PENDING,
    )
    for field in _PROVIDER_WRITE_FIELDS:
        if field in data:
            setattr(provider, field, data[field])
    provider.save()
    return serialize_provider(provider, include_private=True)


def update_provider(
    provider_id: int,
    *,
    session_hash: str,
    is_staff: bool,
    data: dict[str, Any],
) -> dict[str, Any] | None:
    provider = _get_provider_or_none(provider_id)
    if provider is None or provider.status == ServiceProvider.DELETED:
        return None
    if not (is_staff or provider.is_owned_by(session_hash)):
        raise OwnershipError(provider_id)
    _apply_provider_fields(provider, data)
    # Owner edits re-enter moderation; staff edits keep current status.
    if not is_staff:
        provider.status = ServiceProvider.PENDING
    provider.save()
    return serialize_provider(provider, include_private=True)


def soft_delete_provider(provider_id: int, *, session_hash: str, is_staff: bool) -> bool | None:
    provider = _get_provider_or_none(provider_id)
    if provider is None or provider.status == ServiceProvider.DELETED:
        return None
    if not (is_staff or provider.is_owned_by(session_hash)):
        raise OwnershipError(provider_id)
    provider.status = ServiceProvider.DELETED
    provider.save(update_fields=['status', 'updated_at'])
    return True


def moderate_provider(provider_id: int, action: str) -> dict[str, Any] | None:
    if action not in VALID_MODERATE_ACTIONS:
        raise ValueError(action)
    provider = _get_provider_or_none(provider_id)
    if provider is None:
        return None
    provider.status = VALID_MODERATE_ACTIONS[action]
    provider.save(update_fields=['status', 'updated_at'])
    return serialize_provider(provider, include_private=True)


# --------------------------------------------------------------------------- #
# Reviews
# --------------------------------------------------------------------------- #

def list_reviews(provider_id: int) -> list[dict[str, Any]]:
    qs = Review.objects.filter(provider_id=provider_id, status=Review.PUBLISHED)
    return [serialize_review(r) for r in qs]


def upsert_review(
    *,
    provider_id: int,
    session_hash: str,
    rating: int,
    text: str = '',
) -> tuple[dict[str, Any], bool] | None:
    provider = _get_provider_or_none(provider_id)
    if provider is None or provider.status == ServiceProvider.DELETED:
        return None
    review, created = Review.objects.update_or_create(
        provider=provider,
        created_by_session_hash=session_hash,
        defaults={
            'island': provider.island,
            'rating': rating,
            'text': text,
            'status': Review.PENDING,
        },
    )
    return serialize_review(review), created


def update_review(
    review_id: int,
    *,
    session_hash: str,
    is_staff: bool,
    data: dict[str, Any],
) -> dict[str, Any] | None:
    try:
        review = Review.objects.get(id=review_id)
    except Review.DoesNotExist:
        return None
    if not (is_staff or review.is_owned_by(session_hash)):
        raise OwnershipError(review_id)
    if 'rating' in data:
        review.rating = data['rating']
    if 'text' in data:
        review.text = data['text']
    if not is_staff:
        review.status = Review.PENDING
    review.save()
    recompute_rating(review.provider)
    return serialize_review(review)


def delete_review(review_id: int, *, session_hash: str, is_staff: bool) -> bool | None:
    try:
        review = Review.objects.get(id=review_id)
    except Review.DoesNotExist:
        return None
    if not (is_staff or review.is_owned_by(session_hash)):
        raise OwnershipError(review_id)
    provider = review.provider
    review.delete()
    recompute_rating(provider)
    return True


def moderate_review(review_id: int, action: str) -> dict[str, Any] | None:
    if action not in VALID_MODERATE_ACTIONS:
        raise ValueError(action)
    try:
        review = Review.objects.get(id=review_id)
    except Review.DoesNotExist:
        return None
    review.status = VALID_MODERATE_ACTIONS[action]
    review.save(update_fields=['status', 'updated_at'])
    recompute_rating(review.provider)
    return serialize_review(review)


def recompute_rating(provider: ServiceProvider) -> None:
    """Set provider.rating/review_count from its PUBLISHED reviews."""
    agg = Review.objects.filter(
        provider=provider, status=Review.PUBLISHED
    ).aggregate(avg=Avg('rating'), count=Count('id'))
    avg = agg['avg'] or 0
    provider.rating = Decimal(str(round(avg, 2)))
    provider.review_count = agg['count'] or 0
    provider.save(update_fields=['rating', 'review_count', 'updated_at'])


# --------------------------------------------------------------------------- #
# Phone normalization (one-off / ops)
# --------------------------------------------------------------------------- #

_PROVIDER_PHONE_FIELDS = ('phone', 'whatsapp')


def fix_provider_phone_numbers(
    *,
    island=None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Normalize ``phone`` and ``whatsapp`` on all service providers to ``+351XXXXXXXXX``."""
    qs = ServiceProvider.objects.unscoped().select_related('island')
    if island is not None:
        qs = qs.filter(island=island)

    scanned = 0
    updated = 0
    unchanged = 0
    skipped_fields = 0
    changes: list[dict[str, Any]] = []

    for provider in qs.iterator():
        scanned += 1
        field_updates: dict[str, str] = {}
        field_skipped: list[str] = []

        for field in _PROVIDER_PHONE_FIELDS:
            raw = getattr(provider, field) or ''
            if not str(raw).strip():
                continue
            normalized = normalize_pt_phone(raw)
            if normalized is None:
                field_skipped.append(field)
                continue
            if normalized != raw:
                field_updates[field] = normalized

        if field_skipped:
            skipped_fields += len(field_skipped)

        if not field_updates:
            unchanged += 1
            continue

        updated += 1
        change_row: dict[str, Any] = {
            'id': provider.id,
            'name': provider.name,
            'island': provider.island.key,
        }
        for field, new_value in field_updates.items():
            change_row[field] = {'from': getattr(provider, field), 'to': new_value}
        changes.append(change_row)

        if not dry_run:
            for field, new_value in field_updates.items():
                setattr(provider, field, new_value)
            provider.save(update_fields=[*field_updates.keys(), 'updated_at'])

    return {
        'dry_run': dry_run,
        'island_key': getattr(island, 'key', None),
        'scanned': scanned,
        'updated': updated,
        'unchanged': unchanged,
        'skipped_fields': skipped_fields,
        'changes': changes,
    }
