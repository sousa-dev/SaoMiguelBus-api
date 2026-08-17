"""Atlas business logic: revision bumps, parish assignment, tombstoning, delta-sync paging."""

from __future__ import annotations

from typing import Any

from django.db import transaction

from atlas.models import (
    AtlasCategory,
    AtlasPoi,
    AtlasRevision,
    AtlasTombstone,
    AtlasTrail,
)
from tenancy.models import Island

# Tombstone retention window (SDD 02 §3.4). A client whose cursor predates the oldest
# surviving tombstone cannot be brought up to date incrementally.
TOMBSTONE_RETENTION_DAYS = 180

SYNC_DEFAULT_LIMIT = 500
SYNC_MAX_LIMIT = 1000


# --------------------------------------------------------------------------------------
# Parish assignment (D6)
# --------------------------------------------------------------------------------------

def assign_parish(entity: AtlasPoi | AtlasTrail) -> None:
    """Resolve nearest parish via weather.ParishProximity. Call before save() on create/move."""
    from weather.services import resolve_parish

    if isinstance(entity, AtlasTrail):
        lat, lon = entity.start_lat, entity.start_lon
    else:
        lat, lon = entity.latitude, entity.longitude

    parish = resolve_parish(
        island=entity.island,
        source_module='atlas',
        source_ref=str(entity.uid),
        lat=lat,
        lon=lon,
    )
    entity.parish = parish
    entity.parish_slug = parish.slug if parish else ''


def backfill_parishes(island: Island) -> int:
    """Recompute parish assignment for every POI/trail with coordinates but no parish yet,
    or whenever parish boundaries change. Re-runnable."""
    updated = 0
    for poi in AtlasPoi.objects.unscoped().filter(island=island):
        assign_parish(poi)
        poi.save(update_fields=['parish', 'parish_slug'])
        updated += 1
    for trail in AtlasTrail.objects.unscoped().filter(island=island, start_lat__isnull=False):
        # Trails resolve parish from the trailhead, not a line-wide centroid.
        proxy = AtlasPoi(uid=trail.uid, island=island, latitude=trail.start_lat, longitude=trail.start_lon)
        assign_parish(proxy)
        trail.parish = proxy.parish
        trail.parish_slug = proxy.parish_slug
        trail.save(update_fields=['parish', 'parish_slug'])
        updated += 1
    return updated


# --------------------------------------------------------------------------------------
# Category assignment — mirrors is_safety_critical onto the POI row (D16)
# --------------------------------------------------------------------------------------

def assign_category(poi: AtlasPoi, category: AtlasCategory) -> None:
    """Set a POI's category and denormalise the safety-critical flag from it.

    A DB CheckConstraint cannot join to AtlasCategory, so is_safety_critical is copied onto
    AtlasPoi here — this is the only place that should set it.
    """
    poi.category = category
    poi.is_safety_critical = category.is_safety_critical


# --------------------------------------------------------------------------------------
# Publish / unpublish — both bump revision; unpublish also tombstones (§3.4)
# --------------------------------------------------------------------------------------

def _entity_type(entity: AtlasPoi | AtlasTrail | AtlasCategory) -> str:
    if isinstance(entity, AtlasPoi):
        return AtlasTombstone.ENTITY_POI
    if isinstance(entity, AtlasTrail):
        return AtlasTombstone.ENTITY_TRAIL
    return AtlasTombstone.ENTITY_CATEGORY


def write_tombstone(entity: AtlasPoi | AtlasTrail | AtlasCategory, *, revision: int) -> AtlasTombstone:
    source = getattr(entity, 'source', '')
    return AtlasTombstone.objects.create(
        island=entity.island,
        entity_type=_entity_type(entity),
        entity_uid=entity.uid,
        source=source,
        revision=revision,
    )


@transaction.atomic
def publish(entity: AtlasPoi | AtlasTrail) -> AtlasPoi | AtlasTrail:
    revision = AtlasRevision.next_for(entity.island)
    entity.is_published = True
    entity.revision = revision
    entity.save(update_fields=['is_published', 'revision', 'updated_at'])
    return entity


@transaction.atomic
def unpublish(entity: AtlasPoi | AtlasTrail) -> AtlasPoi | AtlasTrail:
    """Unpublishing must be visible to offline clients exactly like a delete (§3.4)."""
    revision = AtlasRevision.next_for(entity.island)
    entity.is_published = False
    entity.revision = revision
    entity.save(update_fields=['is_published', 'revision', 'updated_at'])
    write_tombstone(entity, revision=revision)
    return entity


@transaction.atomic
def bump_revision(entity: AtlasPoi | AtlasTrail | AtlasCategory, *, fields: list[str]) -> int:
    """Allocate a new revision and save it plus the given changed fields."""
    revision = AtlasRevision.next_for(entity.island)
    entity.revision = revision
    entity.save(update_fields=[*fields, 'revision'])
    return revision


# --------------------------------------------------------------------------------------
# Delta-sync paging (SDD 02 §4.1)
# --------------------------------------------------------------------------------------

def oldest_surviving_tombstone_revision(island: Island) -> int | None:
    from django.utils import timezone

    cutoff = timezone.now() - timezone.timedelta(days=TOMBSTONE_RETENTION_DAYS)
    oldest = (
        AtlasTombstone.objects.unscoped()
        .filter(island=island, created_at__gte=cutoff)
        .order_by('revision')
        .values_list('revision', flat=True)
        .first()
    )
    return oldest


def current_revision(island: Island) -> int:
    return AtlasRevision.objects.filter(island=island).values_list('current', flat=True).first() or 0


def needs_full_resync(island: Island, since: int) -> bool:
    """Whether the client's cursor can still converge, or has to be thrown away.

    Two ways it cannot converge — one from each end of the range:

    1. **Cursor from the future** (`since > current`). Revisions only ever increase, and a
       client only ever sets `since` from a revision this server handed it, so a cursor above
       our own counter means the client's state came from a *different* database — a seed built
       against the wrong environment, a restored dump, a rebuilt tenant. `revision__gt=since`
       then matches nothing, forever: the client syncs "successfully", applies zero rows, and
       silently never receives another update. Shipped exactly that way once (atlas-seed.db was
       built from a dev database whose counters ran ~3-6x ahead of production), and every
       install was a permanent no-op until this check existed.
    2. **Cursor too old** (`since < oldest surviving tombstone`). Deletions it never saw have
       already been pruned, so replaying forward would leave orphaned rows behind.
    """
    if since <= 0:
        return False
    if since > current_revision(island):
        return True
    oldest = oldest_surviving_tombstone_revision(island)
    if oldest is None:
        return False
    return since < oldest


def _localize(value: dict[str, Any] | None, locale: str) -> dict[str, Any] | None:
    if not value:
        return value
    fallback = value.get('pt')
    return {'pt': fallback, locale: value.get(locale, fallback)} if locale != 'pt' else value


def serialize_category(category: AtlasCategory) -> dict[str, Any]:
    return {
        'slug': category.slug,
        'name': category.name,
        'group': category.group,
        'icon': category.icon,
        'color': category.color,
        'sortOrder': category.sort_order,
        'isSafetyCritical': category.is_safety_critical,
        'revision': category.revision,
    }


def serialize_poi(poi: AtlasPoi) -> dict[str, Any]:
    return {
        'uid': str(poi.uid),
        'category': poi.category.slug,
        'kind': poi.kind,
        'tier': poi.tier,
        'name': poi.name,
        'description': poi.description,
        'latitude': poi.latitude,
        'longitude': poi.longitude,
        'elevationM': poi.elevation_m,
        'parishSlug': poi.parish_slug,
        'media': poi.media,
        'openingHours': poi.opening_hours,
        'tips': poi.tips,
        'accessibility': poi.accessibility,
        # Contact/reference fields (phone, website, address) — real data that was captured on
        # import but never reached clients (SDD 07 §4). Deliberately not source-specific: the
        # client just renders whatever keys happen to be present.
        'externalRefs': poi.external_refs,
        'isSafetyCritical': poi.is_safety_critical,
        'isSafetyReviewed': poi.is_safety_reviewed,
        'revision': poi.revision,
        'updatedAt': poi.updated_at.isoformat(),
    }


def serialize_trail(trail: AtlasTrail) -> dict[str, Any]:
    return {
        'uid': str(trail.uid),
        'name': trail.name,
        'description': trail.description,
        'difficulty': trail.difficulty,
        'distanceKm': trail.distance_km,
        'durationMin': trail.duration_min,
        'ascentM': trail.ascent_m,
        'shape': trail.shape,
        'startLat': trail.start_lat,
        'startLon': trail.start_lon,
        'parishSlug': trail.parish_slug,
        'geojson': trail.geojson,
        'gpxUrl': trail.gpx_url,
        'payload': trail.payload,
        'stages': [
            {'name': s.name, 'sequence': s.sequence, 'geojson': s.geojson}
            for s in trail.stages.all().order_by('sequence')
        ],
        'revision': trail.revision,
    }


def serialize_tombstone(tombstone: AtlasTombstone) -> dict[str, Any]:
    return {
        'entityType': tombstone.entity_type,
        'uid': str(tombstone.entity_uid),
        'revision': tombstone.revision,
    }


def build_atlas_stats(*, island: Island | None = None) -> dict[str, Any]:
    """Published catalogue totals for marketing / landing pages.

    When ``island`` is set, counts are scoped to that tenant. Otherwise returns
    archipelago-wide totals (all islands).
    """
    pois = AtlasPoi.objects.unscoped().filter(is_published=True, is_active=True)
    trails = AtlasTrail.objects.unscoped().filter(is_published=True, is_active=True)
    categories = AtlasCategory.objects.unscoped().filter(is_active=True)

    if island is not None:
        pois = pois.filter(island=island)
        trails = trails.filter(island=island)
        categories = categories.filter(island=island)
        island_count = 1
    else:
        island_count = (
            Island.objects.filter(
                id__in=AtlasPoi.objects.unscoped()
                .filter(is_published=True, is_active=True)
                .values_list('island_id', flat=True)
                .distinct(),
            ).count()
        )

    return {
        'pois': pois.count(),
        'trails': trails.count(),
        'categories': categories.count(),
        'islands': island_count,
    }


def build_sync_page(island: Island, *, since: int, limit: int) -> dict[str, Any]:
    """One page of the delta-sync response. `revision` in the response is the page's max —
    the client's next cursor. Ordering by revision keeps paging stable under concurrent writes.
    """
    limit = max(1, min(limit, SYNC_MAX_LIMIT))

    categories = list(
        AtlasCategory.objects.unscoped()
        .filter(island=island, revision__gt=since, is_active=True)
        .order_by('revision')[:limit],
    )
    pois = list(
        AtlasPoi.objects.unscoped()
        .filter(island=island, revision__gt=since, is_published=True, is_active=True)
        .select_related('category')
        .order_by('revision')[:limit],
    )
    trails = list(
        AtlasTrail.objects.unscoped()
        .filter(island=island, revision__gt=since, is_published=True, is_active=True)
        .prefetch_related('stages')
        .order_by('revision')[:limit],
    )
    deleted = list(
        AtlasTombstone.objects.unscoped()
        .filter(island=island, revision__gt=since)
        .order_by('revision')[:limit],
    )

    buckets = (categories, pois, trails, deleted)

    # The cursor may only advance to a revision every bucket has fully delivered. Each bucket
    # is limited independently, so a bucket that came back full (len == limit) still has rows
    # above its own last revision — the cursor has to stop there, at the *lowest* such point.
    #
    # Taking max() across all buckets instead silently strands rows: with trails imported last
    # they occupy the top of the range (e.g. 3027-3056) while POIs sit at 51-580 truncated at
    # 500, so the cursor jumped to 3056 and POIs 581-3026 were never requested again. A full
    # sync from zero delivered 500 of São Miguel's 2796 POIs and reported success. Rows above
    # the chosen cursor are simply re-sent next page, which is free — upserts are idempotent.
    truncated_maxes = [
        max(row.revision for row in rows) for rows in buckets if len(rows) == limit
    ]
    if truncated_maxes:
        page_max = min(truncated_maxes)
    else:
        page_revisions = [since]
        for rows in buckets:
            page_revisions += [row.revision for row in rows]
        page_max = max(page_revisions)

    current = current_revision(island)
    has_more = bool(truncated_maxes) or page_max < current

    return {
        'revision': page_max,
        # The island's true current revision — i.e. what `revision` converges to once
        # `has_more` goes false. Lets the client show real sync progress (applied/total)
        # instead of an unbounded "please wait" spinner (SDD 03 §5, added retroactively once
        # a real multi-thousand-row first sync made that spinner useless).
        'total_revision': current,
        'has_more': has_more,
        'full_resync': needs_full_resync(island, since),
        'counts': {
            'pois': len(pois),
            'trails': len(trails),
            'categories': len(categories),
            'deleted': len(deleted),
        },
        'categories': [serialize_category(c) for c in categories],
        'pois': [serialize_poi(p) for p in pois],
        'trails': [serialize_trail(t) for t in trails],
        'deleted': [serialize_tombstone(d) for d in deleted],
    }
