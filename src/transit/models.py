"""Normalized GTFS-inspired transit schema."""

from __future__ import annotations

from django.db import models
from django.utils import timezone

from tenancy.models import TenantScopedModel


DATASET_LEGACY = 'legacy'
DATASET_AZORESBUS = 'azoresbus'
DATASET_CHOICES = [
    (DATASET_LEGACY, 'Legacy network'),
    (DATASET_AZORESBUS, 'AzoresBus 2026'),
]


def dataset_field():
    """The network a row belongs to.

    Defaults to ``legacy`` so every pre-existing row is correctly tagged by the
    default and no data migration is needed. Readers must filter on it: legacy
    and AzoresBus share line codes and stop names, so an unfiltered query mixes
    two networks (98 B4).
    """
    return models.CharField(
        max_length=16,
        choices=DATASET_CHOICES,
        default=DATASET_LEGACY,
        db_index=True,
    )


class Operator(TenantScopedModel):
    name = models.CharField(max_length=64)
    contact = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = [('island', 'name')]
        ordering = ['name']

    def __str__(self) -> str:
        return self.name


class Calendar(TenantScopedModel):
    WEEKDAY = 'WEEKDAY'
    SATURDAY = 'SATURDAY'
    SUNDAY = 'SUNDAY'
    SERVICE_CHOICES = [
        (WEEKDAY, 'Weekday'),
        (SATURDAY, 'Saturday'),
        (SUNDAY, 'Sunday'),
    ]

    service_type = models.CharField(max_length=16, choices=SERVICE_CHOICES)

    class Meta:
        unique_together = [('island', 'service_type')]
        ordering = ['service_type']

    def __str__(self) -> str:
        return self.service_type


class ServicePattern(TenantScopedModel):
    """Which dates a set of trips operates on. GTFS calendar + calendar_dates.

    Replaces the three-row `Calendar` for anything date-resolved. Calendar has
    exactly three rows per island and cannot express "Tuesday and Thursday,
    school term only" (line 112), "Wednesday only" (102 journey 1009), or
    "38 journeys from 14 September, 33 in July" (307). See 98 B0.

    These rules are DERIVED from a bounded sample, not published by the
    operator. `confidence` says so and must stay honest.
    """

    CONFIDENCE_SAMPLED = 'sampled'
    CONFIDENCE_OFFICIAL = 'official'
    CONFIDENCE_CHOICES = [
        (CONFIDENCE_SAMPLED, 'Inferred from observed dates'),
        (CONFIDENCE_OFFICIAL, 'Published by the operator'),
    ]

    WEEKDAY_FIELDS = (
        'monday', 'tuesday', 'wednesday', 'thursday', 'friday',
        'saturday', 'sunday',
    )

    dataset = dataset_field()
    key = models.CharField(max_length=64, db_index=True)

    monday = models.BooleanField(default=False)
    tuesday = models.BooleanField(default=False)
    wednesday = models.BooleanField(default=False)
    thursday = models.BooleanField(default=False)
    friday = models.BooleanField(default=False)
    saturday = models.BooleanField(default=False)
    sunday = models.BooleanField(default=False)

    start_date = models.DateField(null=True, blank=True)   # null => unbounded
    end_date = models.DateField(null=True, blank=True)
    # We have evidence the service stops but the sample is too sparse to say
    # when. Flagged rather than guessed (02 section 3.3).
    end_unknown = models.BooleanField(default=False)
    # Weekdays the sample could not settle. Recorded, never averaged.
    ambiguous_weekdays = models.JSONField(default=list, blank=True)

    derived_from_run = models.ForeignKey(
        'azoresbus.SyncRun', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='derived_patterns',
    )
    confidence = models.CharField(max_length=16, choices=CONFIDENCE_CHOICES,
                                  default=CONFIDENCE_SAMPLED)

    class Meta:
        unique_together = [('island', 'dataset', 'key')]
        indexes = [models.Index(fields=['island', 'dataset'])]

    def __str__(self) -> str:
        mask = ''.join(
            '1' if getattr(self, name) else '0' for name in self.WEEKDAY_FIELDS
        )
        return f'{self.key} ({mask})'

    def runs_on_weekday(self, weekday: int) -> bool:
        """weekday is Python's Monday=0 .. Sunday=6."""
        return bool(getattr(self, self.WEEKDAY_FIELDS[weekday]))


class ServiceException(TenantScopedModel):
    """GTFS calendar_dates: force a date on or off for one pattern.

    Populated from upstream behaviour, not just our Holiday table: a weekday
    whose journey set equals that route's Sunday set is a holiday as far as
    upstream is concerned, whatever our list says (02 section 4.1).
    """

    ADDED = 1
    REMOVED = 2
    TYPE_CHOICES = [(ADDED, 'Added'), (REMOVED, 'Removed')]

    service = models.ForeignKey(ServicePattern, on_delete=models.CASCADE,
                                related_name='exceptions')
    date = models.DateField(db_index=True)
    exception_type = models.PositiveSmallIntegerField(choices=TYPE_CHOICES)

    class Meta:
        unique_together = [('service', 'date')]
        indexes = [models.Index(fields=['service', 'date'])]

    def __str__(self) -> str:
        return f'{self.service.key} {self.date} {self.get_exception_type_display()}'


class Stop(TenantScopedModel):
    dataset = dataset_field()
    name = models.CharField(max_length=200)
    cleaned_name = models.CharField(max_length=200, db_index=True)
    latitude = models.FloatField()
    longitude = models.FloatField()

    class Meta:
        indexes = [
            models.Index(fields=['island', 'cleaned_name']),
            models.Index(fields=['island', 'dataset', 'cleaned_name']),
        ]
        ordering = ['name']
        constraints = [
            # `cleaned_name` is this model's only identity -- there is no
            # upstream id -- and `_import_stops` reconciles on it. Nothing
            # enforced that before, so a double-write could silently overwrite
            # a row's coordinates, or raise MultipleObjectsReturned and abort
            # the whole atomic import.
            #
            # Scoped to AzoresBus because legacy deliberately carries
            # duplicate-named rows (`serialize_legacy_stops_v2` synthesises
            # alias rows from them), so a global constraint would be a bet on
            # data this change does not touch.
            models.UniqueConstraint(
                fields=['island', 'dataset', 'cleaned_name'],
                condition=models.Q(dataset='azoresbus'),
                name='uniq_azoresbus_stop_cleaned_name',
            ),
        ]

    def __str__(self) -> str:
        return self.name


class StopAlias(TenantScopedModel):
    """A folded name that used to identify a stop, and still must.

    Canonicalization rewrites 437 of the 814 AzoresBus stop names, which moves
    their `cleaned_name` -- and `cleaned_name` is what every lookup in this
    codebase resolves against. Without this table, a favourite starred in the
    app, a deep link pasted into WhatsApp and a shared `?origin=` URL all stop
    resolving on the day the rename ships.

    Rows are written from the VERBATIM upstream spelling at import, and are
    never deleted when upstream stops emitting one. That permanence is the
    entire point: the day AzoresBus fixes its own spelling of
    `S. VICENTE FERREIRA`, a computed index would lose the alias and every
    link built on it would break. A stored row survives upstream's cleanup.
    """

    dataset = dataset_field()
    stop = models.ForeignKey(Stop, on_delete=models.CASCADE, related_name='aliases')
    cleaned_alias = models.CharField(max_length=200, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['island', 'dataset', 'cleaned_alias'],
                name='uniq_stop_alias_per_dataset',
            ),
        ]
        indexes = [models.Index(fields=['island', 'dataset', 'cleaned_alias'])]

    def __str__(self) -> str:
        return f'{self.cleaned_alias} -> {self.stop.name}'


class Line(TenantScopedModel):
    dataset = dataset_field()
    operator = models.ForeignKey(Operator, on_delete=models.PROTECT, related_name='lines')
    code = models.CharField(max_length=32)
    display_name = models.CharField(max_length=120, blank=True, default='')
    disabled = models.BooleanField(default=False)

    class Meta:
        # ('island', 'code') cannot hold: legacy already has 101, 102, 112,
        # 301... and so does AzoresBus (98 B4).
        unique_together = [('island', 'dataset', 'code')]
        ordering = ['code']

    def __str__(self) -> str:
        return self.code


class RouteInfo(TenantScopedModel):
    # Disruption notices describe an operator. After cutover the legacy rows
    # describe a network that no longer runs (02 section 3.8).
    dataset = dataset_field()
    text = models.JSONField(default=dict, blank=True)
    source = models.CharField(max_length=500, blank=True, default='')
    company = models.CharField(max_length=32, blank=True, default='')
    start = models.DateTimeField(null=True, blank=True)
    end = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return self.company or str(self.pk)


class Trip(TenantScopedModel):
    SOURCE_OPERATOR = 'operator'
    SOURCE_GMAPS = 'gmaps'
    SOURCE_CHOICES = [
        (SOURCE_OPERATOR, 'Operator timetable'),
        (SOURCE_GMAPS, 'Google Maps derived'),
    ]

    # Denormalised from `line` on purpose: search filters on Trip and the extra
    # join would sit on the hot path.
    dataset = dataset_field()
    line = models.ForeignKey(Line, on_delete=models.CASCADE, related_name='trips')
    # Nullable now: AzoresBus trips are date-resolved through `service`, and
    # legacy trips keep their Calendar until it is retired separately. Every
    # existing row and query stays valid through the migration.
    calendar = models.ForeignKey(Calendar, on_delete=models.PROTECT,
                                 related_name='trips', null=True, blank=True)
    service = models.ForeignKey(ServicePattern, on_delete=models.PROTECT,
                                related_name='trips', null=True, blank=True)
    headsign = models.CharField(max_length=200, blank=True, default='')
    direction = models.CharField(max_length=32, blank=True, default='')
    likes = models.IntegerField(default=0)
    dislikes = models.IntegerField(default=0)
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES, default=SOURCE_OPERATOR)
    information = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['island', 'line', 'calendar']),
            models.Index(fields=['island', 'dataset', 'source']),
            models.Index(fields=['island', 'dataset', 'service']),
        ]

    def __str__(self) -> str:
        when = self.calendar.service_type if self.calendar_id else (
            self.service.key if self.service_id else 'no service'
        )
        return f'{self.line.code} ({when})'


class StopTime(TenantScopedModel):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='stop_times')
    stop = models.ForeignKey(Stop, on_delete=models.PROTECT, related_name='stop_times')
    sequence = models.PositiveIntegerField()
    departure_time = models.TimeField()
    arrival_time = models.TimeField(null=True, blank=True)
    # Night journeys wrap to zero mid-trip (98 B2). Storing 00:10 without an
    # offset and then ordering by the bare TimeField reorders the trip, so
    # every sort must use (day_offset, departure_time) or sequence.
    day_offset = models.PositiveSmallIntegerField(default=0)
    # Which physical pole. Collapsing 1456 stops to 816 names for the picker
    # would otherwise destroy the side-of-road information upstream gives us.
    external_stop = models.ForeignKey(
        'azoresbus.ExternalStop', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='stop_times',
    )

    class Meta:
        unique_together = [('trip', 'sequence')]
        ordering = ['trip', 'sequence']

    def __str__(self) -> str:
        return f'{self.trip_id} #{self.sequence} {self.stop.name}'


class Holiday(TenantScopedModel):
    date = models.DateField()
    name = models.CharField(max_length=120)

    class Meta:
        unique_together = [('island', 'date')]
        ordering = ['date']

    def __str__(self) -> str:
        return f'{self.name} ({self.date})'


class StopGroup(TenantScopedModel):
    # Live, not dead code: services/ads.py targets ads by stop-name group.
    dataset = dataset_field()
    name = models.CharField(max_length=64)
    stop_names = models.JSONField(default=list)

    class Meta:
        unique_together = [('island', 'dataset', 'name')]

    def __str__(self) -> str:
        return self.name


class Ad(TenantScopedModel):
    entity = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True, default='')
    media = models.CharField(max_length=1000)
    start = models.DateTimeField()
    end = models.DateTimeField()
    action = models.CharField(max_length=32, blank=True, default='')
    target = models.CharField(max_length=255, blank=True, default='')
    advertise_on = models.CharField(max_length=100)
    platform = models.CharField(max_length=16)
    status = models.CharField(max_length=16, default='pending')
    seen = models.IntegerField(default=0)
    clicked = models.IntegerField(default=0)

    def __str__(self) -> str:
        return self.entity


class AdEvent(TenantScopedModel):
    """Time-stamped ad impression/click, complementing the lifetime counters on Ad.

    Not routed through AnalyticsEvent: ads are served to everyone regardless of
    analytics consent, and these rows carry no session or personal data.
    """

    KIND_IMPRESSION = 'impression'
    KIND_CLICK = 'click'

    ad = models.ForeignKey(Ad, on_delete=models.CASCADE, related_name='events')
    kind = models.CharField(max_length=16, db_index=True)
    platform = models.CharField(max_length=16, blank=True, default='')
    occurred_at = models.DateTimeField(db_index=True, default=timezone.now)

    class Meta:
        db_table = 'transit_ad_event'
        indexes = [
            models.Index(fields=['island', 'kind', 'occurred_at']),
            models.Index(fields=['ad', 'kind', 'occurred_at']),
        ]

    def __str__(self) -> str:
        return f'{self.ad_id} {self.kind} @ {self.occurred_at:%Y-%m-%d %H:%M}'
