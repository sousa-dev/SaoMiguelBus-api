"""Traffic business logic: CRUD, geo search, voting, lifecycle, serialization.

Reports are **public on create** (no moderation queue). Reads/writes assume the
active island is bound (v3 views wrap calls in ``with for_island(request.island):``).
Creates pass ``island`` explicitly. Ownership is pseudonymous via
``created_by_session_hash``. ``run_lifecycle`` runs unscoped across islands from
the Celery beat task (time-driven transitions are tenant-agnostic).
"""

from __future__ import annotations

import math
from datetime import timedelta
from typing import Any

from django.utils import timezone

from traffic.models import TrafficCategory, TrafficConfirmation, TrafficReport

MAX_LIMIT = 200
DEFAULT_LIMIT = 100
DENY_THRESHOLD = 3
EARTH_RADIUS_KM = 6371.0


class TrafficError(Exception):
    """Base for traffic service errors."""


class OwnershipError(TrafficError):
    """Raised when a non-owner / non-staff attempts a restricted write."""


class CategoryNotFound(TrafficError):
    """Raised when a write references an unknown category slug."""


class LocationImplausible(TrafficError):
    """Raised when report coordinates fall outside the island radius."""


class SchedulingNotAllowed(TrafficError):
    """Raised when active_from is set on a non-schedulable category."""


# --------------------------------------------------------------------------- #
# Geo helpers
# --------------------------------------------------------------------------- #

def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lng / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(a))


# --------------------------------------------------------------------------- #
# Serialization
# --------------------------------------------------------------------------- #

def serialize_category(category: TrafficCategory) -> dict[str, Any]:
    return {
        'id': category.id,
        'name': category.name,
        'slug': category.slug,
        'icon': category.icon,
        'defaultTtlMinutes': category.default_ttl_minutes,
        'isSchedulable': category.is_schedulable,
        'order': category.order,
    }


def serialize_report(report: TrafficReport) -> dict[str, Any]:
    return {
        'id': report.id,
        'status': report.status,
        'category': {
            'id': report.category_id,
            'name': report.category.name,
            'slug': report.category.slug,
            'icon': report.category.icon,
        },
        'latitude': report.latitude,
        'longitude': report.longitude,
        'description': report.description,
        'road': report.road,
        'confidence': {'confirm': report.confirm_count, 'deny': report.deny_count},
        'activeFrom': report.active_from.isoformat() if report.active_from else None,
        'activeUntil': report.active_until.isoformat() if report.active_until else None,
        'expiresAt': report.expires_at.isoformat() if report.expires_at else None,
        'createdAt': report.created_at.isoformat(),
    }


# --------------------------------------------------------------------------- #
# Categories
# --------------------------------------------------------------------------- #

def list_categories() -> list[dict[str, Any]]:
    return [serialize_category(c) for c in TrafficCategory.objects.all()]


def _resolve_category(slug: str) -> TrafficCategory:
    try:
        return TrafficCategory.objects.get(slug=slug)
    except TrafficCategory.DoesNotExist as exc:
        raise CategoryNotFound(slug) from exc


# --------------------------------------------------------------------------- #
# Reports — reads
# --------------------------------------------------------------------------- #

def list_reports(
    *,
    lat: float | None = None,
    lng: float | None = None,
    radius_km: float | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    category: str | None = None,
    include_scheduled: bool = False,
    limit: int = DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    statuses = [TrafficReport.ACTIVE]
    if include_scheduled:
        statuses.append(TrafficReport.SCHEDULED)

    qs = TrafficReport.objects.select_related('category').filter(status__in=statuses)
    if category:
        qs = qs.filter(category__slug=category)

    if bbox is not None:
        min_lng, min_lat, max_lng, max_lat = bbox
        qs = qs.filter(
            latitude__gte=min_lat, latitude__lte=max_lat,
            longitude__gte=min_lng, longitude__lte=max_lng,
        )

    limit = max(1, min(limit, MAX_LIMIT))

    if lat is not None and lng is not None and radius_km is not None:
        within = [
            r for r in qs
            if haversine_km(lat, lng, r.latitude, r.longitude) <= radius_km
        ]
        within.sort(key=lambda r: haversine_km(lat, lng, r.latitude, r.longitude))
        return [serialize_report(r) for r in within[:limit]]

    return [serialize_report(r) for r in qs[:limit]]


def _get_report_or_none(report_id: int) -> TrafficReport | None:
    try:
        return TrafficReport.objects.select_related('category').get(id=report_id)
    except TrafficReport.DoesNotExist:
        return None


def get_report(report_id: int, *, is_staff: bool = False) -> dict[str, Any] | None:
    report = _get_report_or_none(report_id)
    if report is None:
        return None
    if report.status == TrafficReport.REMOVED and not is_staff:
        return None
    return serialize_report(report)


# --------------------------------------------------------------------------- #
# Reports — writes
# --------------------------------------------------------------------------- #

def _check_plausible(island, latitude: float, longitude: float) -> None:
    distance = haversine_km(island.center_lat, island.center_lng, latitude, longitude)
    if distance > island.radius_km:
        raise LocationImplausible(f'{distance:.1f}km from island center')


def create_report(
    *,
    island,
    session_hash: str,
    category_slug: str,
    latitude: float,
    longitude: float,
    description: str = '',
    road: str = '',
    active_from=None,
    active_until=None,
) -> dict[str, Any]:
    category = _resolve_category(category_slug)
    _check_plausible(island, latitude, longitude)

    now = timezone.now()
    ttl = timedelta(minutes=category.default_ttl_minutes)

    if active_from and active_from > now:
        if not category.is_schedulable:
            raise SchedulingNotAllowed(category_slug)
        status = TrafficReport.SCHEDULED
        expires_at = active_until or (active_from + ttl)
    else:
        active_from = None
        status = TrafficReport.ACTIVE
        expires_at = active_until or (now + ttl)

    report = TrafficReport.objects.create(
        island=island,
        category=category,
        created_by_session_hash=session_hash,
        latitude=latitude,
        longitude=longitude,
        description=description,
        road=road,
        active_from=active_from,
        active_until=active_until,
        expires_at=expires_at,
        status=status,
    )
    return serialize_report(report)


_REPORT_WRITE_FIELDS = ('latitude', 'longitude', 'description', 'road')


def update_report(
    report_id: int,
    *,
    session_hash: str,
    is_staff: bool,
    data: dict[str, Any],
) -> dict[str, Any] | None:
    report = _get_report_or_none(report_id)
    if report is None or report.status == TrafficReport.REMOVED:
        return None
    if not (is_staff or report.is_owned_by(session_hash)):
        raise OwnershipError(report_id)
    for field in _REPORT_WRITE_FIELDS:
        if field in data:
            setattr(report, field, data[field])
    report.save()
    return serialize_report(report)


def soft_delete_report(report_id: int, *, session_hash: str, is_staff: bool) -> bool | None:
    report = _get_report_or_none(report_id)
    if report is None or report.status == TrafficReport.REMOVED:
        return None
    if not (is_staff or report.is_owned_by(session_hash)):
        raise OwnershipError(report_id)
    report.status = TrafficReport.REMOVED
    report.save(update_fields=['status', 'updated_at'])
    return True


# --------------------------------------------------------------------------- #
# Confirmations (voting)
# --------------------------------------------------------------------------- #

def upsert_confirmation(
    *,
    report_id: int,
    session_hash: str,
    vote: str,
) -> tuple[dict[str, Any], bool] | None:
    report = _get_report_or_none(report_id)
    if report is None or report.status in (TrafficReport.REMOVED, TrafficReport.EXPIRED):
        return None

    _, created = TrafficConfirmation.objects.update_or_create(
        report=report,
        session_hash=session_hash,
        defaults={'island': report.island, 'vote': vote},
    )
    _recompute_confidence(report)
    return serialize_report(report), created


def _recompute_confidence(report: TrafficReport) -> None:
    votes = TrafficConfirmation.objects.filter(report=report)
    confirm = votes.filter(vote=TrafficConfirmation.STILL_THERE).count()
    deny = votes.filter(vote=TrafficConfirmation.GONE).count()
    report.confirm_count = confirm
    report.deny_count = deny

    if deny >= DENY_THRESHOLD:
        report.status = TrafficReport.EXPIRED
    elif report.status == TrafficReport.ACTIVE:
        # A fresh "still there" extends life by half the category TTL, capped
        # at one full TTL ahead of now.
        ttl = timedelta(minutes=report.category.default_ttl_minutes)
        now = timezone.now()
        extended = report.expires_at + (ttl / 2)
        report.expires_at = min(extended, now + ttl)

    report.save(update_fields=['confirm_count', 'deny_count', 'status', 'expires_at', 'updated_at'])


# --------------------------------------------------------------------------- #
# Lifecycle (Celery)
# --------------------------------------------------------------------------- #

def run_lifecycle(*, now=None) -> dict[str, int]:
    """Activate due scheduled reports and expire stale active ones.

    Runs unscoped across all islands — these transitions are time-driven and
    tenant-agnostic (explicit cross-tenant Celery operation per SDD/11 §3).
    Idempotent and re-runnable.
    """
    now = now or timezone.now()

    activated = (
        TrafficReport.objects.unscoped()
        .filter(status=TrafficReport.SCHEDULED, active_from__lte=now)
        .update(status=TrafficReport.ACTIVE)
    )
    expired = (
        TrafficReport.objects.unscoped()
        .filter(status=TrafficReport.ACTIVE, expires_at__lte=now)
        .update(status=TrafficReport.EXPIRED)
    )
    return {'activated': activated, 'expired': expired}
