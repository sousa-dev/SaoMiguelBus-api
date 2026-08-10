"""Interurban bus stops from our own transit.Stop table (SDD 07 §4). Direct ORM read."""

from __future__ import annotations

from typing import Iterator

from atlas.importers.base import BaseImporter, ImportRow
from atlas.models import AtlasPoi
from transit.models import Stop


class TransitImporter(BaseImporter):
    SOURCE = AtlasPoi.SOURCE_TRANSIT

    def rows(self) -> Iterator[ImportRow]:
        for stop in Stop.objects.filter(island=self.island).order_by('name'):
            yield ImportRow(
                ref=stop.cleaned_name,
                name={'pt': stop.name, 'en': stop.name},
                latitude=stop.latitude,
                longitude=stop.longitude,
                category_slug='bus-stop',
                kind=AtlasPoi.KIND_POI,
                tier=AtlasPoi.TIER_STANDARD,
                external_refs={'transitStopId': stop.pk, 'cleanedName': stop.cleaned_name},
            )
