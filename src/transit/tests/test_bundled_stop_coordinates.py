"""Bundled legacy stop coordinate sanity checks."""

from __future__ import annotations

import re
from pathlib import Path

from django.test import TestCase

from shared.geo import is_within_island_radius
from tenancy.services import get_or_create_default_island

STOPS_TXT = (
    Path(__file__).resolve().parents[3]
    / 'legacy'
    / 'scripts'
    / 'data'
    / 'stops.txt'
)
STOP_LINE = re.compile(
    r'Stop\("(?P<name>.+?)", Location\((?P<lat>[-\d.]+), (?P<lon>[-\d.]+)\)\)',
)


class BundledStopCoordinatesTestCase(TestCase):
    def test_bundled_stops_txt_coordinates_are_on_island(self):
        island = get_or_create_default_island()
        invalid: list[str] = []

        for line in STOPS_TXT.read_text(encoding='utf-8').splitlines():
            match = STOP_LINE.match(line.strip())
            if match is None:
                continue
            name = match.group('name')
            lat = float(match.group('lat'))
            lon = float(match.group('lon'))
            if not is_within_island_radius(
                lat,
                lon,
                center_lat=island.center_lat,
                center_lng=island.center_lng,
                radius_km=island.radius_km,
            ):
                invalid.append(f'{name}: ({lat}, {lon})')

        self.assertEqual(invalid, [], f'Invalid bundled stop coordinates: {invalid}')
