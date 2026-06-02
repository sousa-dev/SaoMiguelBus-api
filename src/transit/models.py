"""Normalized GTFS-inspired transit schema."""

from __future__ import annotations

from django.db import models

from tenancy.models import TenantScopedModel


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


class Stop(TenantScopedModel):
    name = models.CharField(max_length=200)
    cleaned_name = models.CharField(max_length=200, db_index=True)
    latitude = models.FloatField()
    longitude = models.FloatField()

    class Meta:
        indexes = [
            models.Index(fields=['island', 'cleaned_name']),
        ]
        ordering = ['name']

    def __str__(self) -> str:
        return self.name


class Line(TenantScopedModel):
    operator = models.ForeignKey(Operator, on_delete=models.PROTECT, related_name='lines')
    code = models.CharField(max_length=32)
    display_name = models.CharField(max_length=120, blank=True, default='')
    disabled = models.BooleanField(default=False)

    class Meta:
        unique_together = [('island', 'code')]
        ordering = ['code']

    def __str__(self) -> str:
        return self.code


class RouteInfo(TenantScopedModel):
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

    line = models.ForeignKey(Line, on_delete=models.CASCADE, related_name='trips')
    calendar = models.ForeignKey(Calendar, on_delete=models.PROTECT, related_name='trips')
    headsign = models.CharField(max_length=200, blank=True, default='')
    direction = models.CharField(max_length=32, blank=True, default='')
    likes = models.IntegerField(default=0)
    dislikes = models.IntegerField(default=0)
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES, default=SOURCE_OPERATOR)
    information = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['island', 'line', 'calendar']),
        ]

    def __str__(self) -> str:
        return f'{self.line.code} ({self.calendar.service_type})'


class StopTime(TenantScopedModel):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='stop_times')
    stop = models.ForeignKey(Stop, on_delete=models.PROTECT, related_name='stop_times')
    sequence = models.PositiveIntegerField()
    departure_time = models.TimeField()
    arrival_time = models.TimeField(null=True, blank=True)

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
    name = models.CharField(max_length=64)
    stop_names = models.JSONField(default=list)

    class Meta:
        unique_together = [('island', 'name')]

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
