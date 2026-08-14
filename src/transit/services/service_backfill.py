"""Give every legacy trip a ServicePattern equivalent to its Calendar.

S3 answers "does this trip run on this ISO date?" through `Trip.service`. Legacy
trips carry only a `Calendar`, so without this back-fill they would vanish from
search the moment it stops filtering on `calendar__service_type` -- deleting the
outgoing network from the app on the day S3 deploys.

`Calendar` is deliberately left in place. Legacy code paths keep reading it, and
it can be retired separately once nothing does.
"""

from __future__ import annotations

from transit.models import (
    DATASET_LEGACY,
    Calendar,
    ServicePattern,
    Trip,
)


# Calendar.service_type -> the weekday flags that mean the same thing.
LEGACY_MASKS: dict[str, dict[str, bool]] = {
    Calendar.WEEKDAY: {
        'monday': True, 'tuesday': True, 'wednesday': True,
        'thursday': True, 'friday': True, 'saturday': False, 'sunday': False,
    },
    Calendar.SATURDAY: {
        'monday': False, 'tuesday': False, 'wednesday': False,
        'thursday': False, 'friday': False, 'saturday': True, 'sunday': False,
    },
    Calendar.SUNDAY: {
        'monday': False, 'tuesday': False, 'wednesday': False,
        'thursday': False, 'friday': False, 'saturday': False, 'sunday': True,
    },
}

# Stable, readable keys -- these are not derived from a sample, so they do not
# need the derivation hash.
LEGACY_KEYS = {
    Calendar.WEEKDAY: 'legacy-weekday',
    Calendar.SATURDAY: 'legacy-saturday',
    Calendar.SUNDAY: 'legacy-sunday',
}


def backfill_legacy_services(island) -> dict[str, int]:
    """Create one ServicePattern per legacy day-type and attach the trips.

    Idempotent: re-running reuses the same patterns and touches only trips that
    still have no `service`.
    """
    patterns: dict[str, ServicePattern] = {}
    created = 0

    for service_type, mask in LEGACY_MASKS.items():
        pattern, was_created = ServicePattern.objects.get_or_create(
            island=island,
            dataset=DATASET_LEGACY,
            key=LEGACY_KEYS[service_type],
            defaults={
                **mask,
                # Legacy service is what we already ship, not an inference from
                # a sample, so it is not 'sampled'.
                'confidence': ServicePattern.CONFIDENCE_OFFICIAL,
            },
        )
        patterns[service_type] = pattern
        created += int(was_created)

    attached = 0
    for service_type, pattern in patterns.items():
        attached += Trip.objects.filter(
            island=island,
            dataset=DATASET_LEGACY,
            calendar__service_type=service_type,
            service__isnull=True,
        ).update(service=pattern)

    return {'patterns_created': created, 'trips_attached': attached}
