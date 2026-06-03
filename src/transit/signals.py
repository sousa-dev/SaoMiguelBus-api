"""Write-triggered ``data_revision`` bumps for offline-bundle staleness.

Any schedule-bearing change to transit data bumps the owning island's
``data_revision`` so the mobile client's offline bundle is detected as stale.
Vote-only ``Trip`` saves (likes/dislikes) are excluded — they do not affect
schedules and would otherwise invalidate every offline cache on every vote.
"""

from __future__ import annotations

from django.db.models.signals import post_delete, post_save

from transit.models import Calendar, Holiday, Line, RouteInfo, Stop, StopTime, Trip
from transit.services.offline_bundle import bump_data_revision, revision_bumps_suppressed

_WATCHED = (Stop, Line, Trip, StopTime, Calendar, Holiday, RouteInfo)
_VOTE_FIELDS = {'likes', 'dislikes'}


def _maybe_bump(instance, update_fields=None) -> None:
    if revision_bumps_suppressed():
        return
    if update_fields is not None and set(update_fields) <= _VOTE_FIELDS:
        return
    island_id = getattr(instance, 'island_id', None)
    if island_id is None:
        return
    bump_data_revision(island_id)


def _on_post_save(sender, instance, update_fields=None, **kwargs):
    _maybe_bump(instance, update_fields)


def _on_post_delete(sender, instance, **kwargs):
    _maybe_bump(instance)


def register_transit_signals() -> None:
    for model in _WATCHED:
        post_save.connect(
            _on_post_save,
            sender=model,
            dispatch_uid=f'transit_rev_save_{model.__name__}',
        )
        post_delete.connect(
            _on_post_delete,
            sender=model,
            dispatch_uid=f'transit_rev_del_{model.__name__}',
        )
