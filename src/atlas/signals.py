"""Tombstone hard deletes.

Unpublishing goes through services.unpublish(), which tombstones explicitly — a signal can't
tell "flipped to False" from "created already False" without a pre_save diff, and the explicit
path is what admin actions and importers already call. This module only covers the rarer case:
a row physically deleted (Django admin delete action, `manage.py shell`, a future admin
"delete" rather than "unpublish"). A client that was offline when a hard delete happened must
still learn about it (SDD 02 §3.4) — a tombstone is the only channel that reaches it.
"""

from __future__ import annotations

from django.db.models.signals import post_delete
from django.dispatch import receiver

from atlas.models import AtlasCategory, AtlasPoi, AtlasRevision, AtlasTombstone, AtlasTrail


@receiver(post_delete, sender=AtlasPoi)
@receiver(post_delete, sender=AtlasTrail)
@receiver(post_delete, sender=AtlasCategory)
def tombstone_on_delete(sender, instance, **kwargs) -> None:
    revision = AtlasRevision.next_for(instance.island)
    entity_type = {
        AtlasPoi: AtlasTombstone.ENTITY_POI,
        AtlasTrail: AtlasTombstone.ENTITY_TRAIL,
        AtlasCategory: AtlasTombstone.ENTITY_CATEGORY,
    }[sender]
    AtlasTombstone.objects.create(
        island=instance.island,
        entity_type=entity_type,
        entity_uid=instance.uid,
        source=getattr(instance, 'source', ''),
        revision=revision,
    )
