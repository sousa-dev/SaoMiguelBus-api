"""Weather cells for transit origin/destination stops."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from tenancy.models import Island
from transit.models import Stop
from transit.services.schedule_phase import resolve_dataset
from transit.services.legacy_import import clean_string
from weather.models import ParishProximity
from weather.services import parish_snapshot, resolve_parish


def _resolve_stop(island: Island, name: str) -> Stop | None:
    cleaned = clean_string(name)
    if not cleaned:
        return None
    # .first() on a two-network table picks an arbitrary network's coordinates.
    dataset = resolve_dataset(island)
    exact = Stop.objects.filter(
        island=island, dataset=dataset, cleaned_name=cleaned,
    ).first()
    if exact is not None:
        return exact
    return (
        Stop.objects.filter(
            island=island, dataset=dataset, cleaned_name__icontains=cleaned,
        )
        .order_by('cleaned_name')
        .first()
    )


def _weather_cell_for_stop(
    island: Island,
    stop: Stop,
    at: datetime | None,
) -> dict[str, Any] | None:
    parish = resolve_parish(
        island,
        'transit_stop',
        str(stop.id),
        stop.latitude,
        stop.longitude,
    )
    if parish is None:
        return None

    proximity = ParishProximity.objects.filter(
        island=island,
        source_module='transit_stop',
        source_ref=str(stop.id),
    ).first()
    distance_km = proximity.distance_km if proximity is not None else None
    return parish_snapshot(parish, at=at, distance_km=distance_km)


def get_route_weather(
    island: Island,
    origin: str,
    destination: str,
    origin_at: datetime | None = None,
    destination_at: datetime | None = None,
) -> dict[str, dict[str, Any] | None]:
    origin_stop = _resolve_stop(island, origin)
    destination_stop = _resolve_stop(island, destination)

    origin_cell = (
        _weather_cell_for_stop(island, origin_stop, origin_at)
        if origin_stop is not None
        else None
    )
    destination_cell = (
        _weather_cell_for_stop(island, destination_stop, destination_at)
        if destination_stop is not None
        else None
    )

    return {
        'origin': origin_cell,
        'destination': destination_cell,
    }
