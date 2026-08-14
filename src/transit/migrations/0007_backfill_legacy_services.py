"""Attach a ServicePattern to every legacy trip.

S3 resolves eligibility through `Trip.service`. Legacy trips carry only a
`Calendar`, so without this they disappear from search the moment it stops
filtering on `calendar__service_type`.

The mapping is inlined rather than imported from
`transit.services.service_backfill` so the migration stays frozen; a test
asserts the two agree.
"""

from django.db import migrations


LEGACY = 'legacy'

# (key, service_type, monday..sunday)
PATTERNS = [
    ('legacy-weekday', 'WEEKDAY', True, True, True, True, True, False, False),
    ('legacy-saturday', 'SATURDAY', False, False, False, False, False, True, False),
    ('legacy-sunday', 'SUNDAY', False, False, False, False, False, False, True),
]

DAYS = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday',
        'saturday', 'sunday')


def backfill(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    ServicePattern = apps.get_model('transit', 'ServicePattern')
    Trip = apps.get_model('transit', 'Trip')

    for island in Island.objects.all():
        for key, service_type, *flags in PATTERNS:
            pattern, _ = ServicePattern.objects.get_or_create(
                island=island,
                dataset=LEGACY,
                key=key,
                defaults={
                    **dict(zip(DAYS, flags)),
                    # Not an inference from a sample: this is the timetable we
                    # already ship.
                    'confidence': 'official',
                },
            )
            Trip.objects.filter(
                island=island,
                dataset=LEGACY,
                calendar__service_type=service_type,
                service__isnull=True,
            ).update(service=pattern)


def unbackfill(apps, schema_editor):
    """Detach and remove only the patterns this migration created."""
    ServicePattern = apps.get_model('transit', 'ServicePattern')
    Trip = apps.get_model('transit', 'Trip')

    keys = [key for key, *_ in PATTERNS]
    Trip.objects.filter(service__key__in=keys).update(service=None)
    ServicePattern.objects.filter(dataset=LEGACY, key__in=keys).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('transit', '0006_service_calendar'),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
