"""Which network is active, and when it changes.

The cutover lives on the server, not in the app (00 Decision 1). A build
installed in June gets correct September timetables because it never had the
decision to make: it sends no `dataset`, and the server resolves one.

S1 lands the resolver with no cutover configured, so every reader resolves to
`legacy` and nothing user-visible changes. S3 adds the date resolution, the
`transitSchedule` bootstrap block and the phase machinery.
"""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

from transit.models import DATASET_AZORESBUS, DATASET_CHOICES, DATASET_LEGACY


AZORES = ZoneInfo('Atlantic/Azores')
FLAG_NAMESPACE = 'azoresbus'

VALID_DATASETS = {value for value, _ in DATASET_CHOICES}


def azoresbus_flags(island) -> dict:
    """The `azoresbus` block of `Island.feature_flags`, editable in admin."""
    flags = island.feature_flags or {}
    block = flags.get(FLAG_NAMESPACE)
    return block if isinstance(block, dict) else {}


def today_in_azores() -> date:
    """All date logic runs in Atlantic/Azores; TIME_ZONE is UTC globally."""
    from django.utils import timezone

    return timezone.now().astimezone(AZORES).date()


def resolve_dataset(island, *, requested: str | None = None,
                    on_date: date | None = None) -> str:
    """Explicit request wins; otherwise the Azores date decides.

    `requested` is the preview toggle and admin/debug only. It must never be
    populated from a cached bootstrap value, and clients must never send
    `dataset=legacy` on a public URL (98 section 4 gap, "Stale bootstrap").
    """
    if requested in VALID_DATASETS:
        return requested

    if island is None:
        # Callers reached via bootstrap can run outside a tenant context.
        return DATASET_LEGACY

    # S3 replaces this with the cutover comparison. Until a cutover instant is
    # configured, the active network is legacy -- which is what makes S1
    # deployable with zero behaviour change.
    return DATASET_LEGACY


__all__ = [
    'AZORES',
    'DATASET_AZORESBUS',
    'DATASET_LEGACY',
    'azoresbus_flags',
    'resolve_dataset',
    'today_in_azores',
]
