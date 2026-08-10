"""Deterministic Atlas entity IDs shared with the Expo trail release bundler.

The Offline Map app seeds trails from the public /api/v3/trails surface at release time,
assigning the same UUIDv5 that this module produces for AtlasTrail rows. Later Atlas
delta-sync therefore updates the seeded row instead of creating a duplicate.

Do **not** change ATLAS_UID_NAMESPACE or the key format without regenerating every
bundled trail catalog and re-importing Atlas trails.
"""

from __future__ import annotations

import uuid

# Fixed project namespace — mirrored verbatim in
# SaoMiguelHub-Tools/Azores-OfflineMap/build/trails/bundle.mjs.
ATLAS_UID_NAMESPACE = uuid.UUID('a20ff1e0-0ff1-4e00-9a05-a71a500ff1e0')


def atlas_trail_uid(island_key: str, source_ref: str) -> uuid.UUID:
    """Stable trail identity: uuid5(namespace, 'trail:{island_key}:{source_ref}')."""
    if not island_key or not source_ref:
        raise ValueError('island_key and source_ref are required for atlas_trail_uid')
    return uuid.uuid5(ATLAS_UID_NAMESPACE, f'trail:{island_key}:{source_ref}')
