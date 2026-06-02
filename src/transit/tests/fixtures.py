"""Shared fixtures for transit tests."""

from __future__ import annotations

from datetime import time

from tenancy.services import get_or_create_default_island
from transit.models import Calendar, Line, Operator, Stop, StopTime, Trip


def ensure_transit_fixtures():
    island = get_or_create_default_island()
    island.feature_flags = {
        **(island.feature_flags or {}),
        'transit': True,
        'maps': True,
    }
    island.save(update_fields=['feature_flags'])

    operator, _ = Operator.objects.get_or_create(
        island=island,
        name='CRP',
        defaults={'contact': {}},
    )
    calendar, _ = Calendar.objects.get_or_create(
        island=island,
        service_type=Calendar.WEEKDAY,
    )
    line, _ = Line.objects.get_or_create(
        island=island,
        code='208',
        defaults={'operator': operator, 'display_name': 'Test line'},
    )
    origin, _ = Stop.objects.get_or_create(
        island=island,
        cleaned_name='ponta delgada',
        defaults={
            'name': 'Ponta Delgada',
            'latitude': 37.7411,
            'longitude': -25.6756,
        },
    )
    destination, _ = Stop.objects.get_or_create(
        island=island,
        cleaned_name='ribeira grande',
        defaults={
            'name': 'Ribeira Grande',
            'latitude': 37.8219,
            'longitude': -25.5186,
        },
    )
    trip, _ = Trip.objects.get_or_create(
        island=island,
        line=line,
        calendar=calendar,
        defaults={'likes': 1, 'dislikes': 0},
    )
    StopTime.objects.get_or_create(
        island=island,
        trip=trip,
        sequence=1,
        defaults={'stop': origin, 'departure_time': time(8, 30)},
    )
    StopTime.objects.get_or_create(
        island=island,
        trip=trip,
        sequence=2,
        defaults={'stop': destination, 'departure_time': time(9, 15)},
    )
    return island, trip, line
