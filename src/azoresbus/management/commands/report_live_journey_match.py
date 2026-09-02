"""Does the live feed's journey id match our imported ExternalJourney ids?

The whole live-for-trip feature rests on one assumption: `journey.id` on a
vehicle's AVL detail is the same id the schedule importer stored as
`ExternalJourney.external_id`. Both come from azb.elevensystems.pt, but it has
never been measured. Run this against production during service hours before
building on it. One detail call per vehicle in service (~30-40).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from azoresbus.models import ExternalJourney
from azoresbus.tracking_client import (
    AzoresbusTrackingError,
    fetch_fleet_locations,
    fetch_vehicle_location,
)
from tenancy.models import Island
from tenancy.services import for_island
from transit.models import DATASET_AZORESBUS


class Command(BaseCommand):
    help = 'Report how many live vehicles carry a journey id we can resolve to a Trip.'

    def add_arguments(self, parser) -> None:
        parser.add_argument('--island', dest='island_key', default='sao-miguel')

    def handle(self, *args, **options) -> None:
        island = Island.objects.get(key=options['island_key'])
        with for_island(island):
            known = set(
                ExternalJourney.objects
                .filter(island=island, dataset=DATASET_AZORESBUS)
                .values_list('external_id', flat=True)
            )
            fleet = fetch_fleet_locations()
            matched: list[tuple] = []
            unmatched: list[tuple] = []
            failed: list[str] = []
            for item in fleet:
                vehicle_id = str(item.get('id', ''))
                try:
                    raw = fetch_vehicle_location(vehicle_id)
                except AzoresbusTrackingError:
                    failed.append(vehicle_id)
                    continue
                journey = raw.get('journey') or {}
                journey_id = str(journey.get('id', ''))
                line = (raw.get('route') or {}).get('nameShort', '')
                row = (vehicle_id, journey_id, line, journey.get('name', ''))
                (matched if journey_id in known else unmatched).append(row)

            self.stdout.write(
                f'fleet={len(fleet)} matched={len(matched)} unmatched={len(unmatched)} '
                f'failed={len(failed)} known_journeys={len(known)}'
            )
            for vehicle_id, journey_id, line, name in unmatched:
                self.stdout.write(
                    f'  unmatched vehicle={vehicle_id} journey={journey_id!r} '
                    f'line={line} name={name}'
                )
