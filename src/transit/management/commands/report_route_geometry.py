"""Report how much route geometry we actually hold, and whether it is usable.

The maps feature draws `ExternalJourney.shape`, which the AzoresBus schedule
importer has been writing since it was built and which nothing has ever read.
"Written by the importer" is not the same as "present in production": the sync
has to have fetched journey DETAILS, since the listing carries no shape at all
(`docs/azoresbus/01-upstream-api-reference.md:196`).

So before trusting a map, check the data. This reports coverage AND decodes a
sample, because a stored string that decodes to two points in the Gulf of Guinea
is worse than an empty one -- it would draw a confident line to nowhere.

    python manage.py report_route_geometry
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from shared.geo import decode_polyline, haversine_km, is_plausible_route_coordinates
from tenancy.models import Island
from transit.models import DATASET_AZORESBUS, Trip

# São Miguel, generously bounded.
BBOX = (37.6, 37.95, -25.9, -25.1)


class Command(BaseCommand):
    help = 'Report stored route-shape coverage and decode a sample.'

    def add_arguments(self, parser):
        parser.add_argument('--island', default='sao-miguel')
        parser.add_argument('--dataset', default=DATASET_AZORESBUS)
        parser.add_argument(
            '--sample', type=int, default=25,
            help='How many shapes to decode and sanity-check (default: 25).',
        )

    def handle(self, *args, **options):
        from azoresbus.models import ExternalJourney

        island = Island.objects.filter(key=options['island']).first()
        if island is None:
            self.stderr.write(f"No island {options['island']!r}")
            return

        dataset = options['dataset']
        trips = Trip.objects.filter(island=island, dataset=dataset)
        journeys = ExternalJourney.objects.filter(island=island, dataset=dataset)
        with_shape = journeys.exclude(shape='')

        trip_count = trips.count()
        journey_count = journeys.count()
        shaped = with_shape.count()

        self.stdout.write(f'island {island.key}  dataset {dataset}')
        self.stdout.write(f'  trips                : {trip_count}')
        self.stdout.write(f'  external journeys    : {journey_count}')
        self.stdout.write(f'  ...carrying a shape  : {shaped}')

        if journey_count:
            self.stdout.write(
                f'  coverage             : {shaped / journey_count * 100:.1f}%'
            )

        if not shaped:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR(
                'No stored shapes. Maps will show nothing. The sync has not '
                'fetched journey details -- fix that before relying on this.'
            ))
            return

        # Coverage alone does not mean usable. Decode a sample.
        usable = offshore = degenerate = 0
        lengths = []
        gaps = []

        for encoded in with_shape.values_list('shape', flat=True)[:options['sample']]:
            points = decode_polyline(encoded)
            if not is_plausible_route_coordinates(points):
                degenerate += 1
                continue
            if any(
                not (BBOX[0] < lat < BBOX[1] and BBOX[2] < lon < BBOX[3])
                for lat, lon in points
            ):
                offshore += 1
                continue
            usable += 1
            lengths.append(
                sum(
                    haversine_km(*points[i], *points[i + 1])
                    for i in range(len(points) - 1)
                )
            )
            gaps.extend(
                haversine_km(*points[i], *points[i + 1]) * 1000
                for i in range(min(len(points) - 1, 200))
            )

        sampled = usable + offshore + degenerate
        self.stdout.write('')
        self.stdout.write(f'  sampled              : {sampled}')
        self.stdout.write(f'    usable             : {usable}')
        self.stdout.write(f'    off-island         : {offshore}')
        self.stdout.write(f'    too short / junk   : {degenerate}')

        if lengths:
            lengths.sort()
            gaps.sort()
            self.stdout.write(
                f'  median path length   : {lengths[len(lengths) // 2]:.1f} km'
            )
            self.stdout.write(
                f'  median vertex gap    : {gaps[len(gaps) // 2]:.0f} m'
            )

        self.stdout.write('')
        if usable == sampled:
            self.stdout.write(self.style.SUCCESS('Geometry looks good — maps can draw it.'))
        else:
            self.stdout.write(self.style.WARNING(
                'Some shapes are unusable. Those trips will render without a '
                'route line; the map degrades rather than lying.'
            ))
