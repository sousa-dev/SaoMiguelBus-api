"""Tests for Azores nearest-island geo helpers."""

from django.test import SimpleTestCase

from seismic.data import AZORES_ISLANDS, bearing, nearest_island


class SeismicGeoTestCase(SimpleTestCase):
    def test_nearest_island_at_sao_miguel_center(self):
        result = nearest_island(37.78, -25.50)
        assert result is not None
        self.assertEqual(result['key'], 'sao-miguel')
        self.assertLess(result['distance_km'], 1.0)

    def test_nearest_island_between_pico_and_faial(self):
        # Mid-channel point slightly closer to Pico
        result = nearest_island(38.52, -28.55)
        assert result is not None
        self.assertIn(result['key'], ('pico', 'faial'))

    def test_nearest_island_distance_positive(self):
        result = nearest_island(37.0, -26.0)
        assert result is not None
        self.assertGreater(result['distance_km'], 0)

    def test_bearing_north(self):
        # Epicentre north of São Miguel center
        self.assertEqual(bearing(37.78, -25.50, 38.5, -25.50), 'N')

    def test_bearing_east(self):
        self.assertEqual(bearing(37.78, -25.50, 37.78, -24.5), 'E')

    def test_bearing_northeast(self):
        self.assertEqual(bearing(37.78, -25.50, 38.2, -24.8), 'NE')

    def test_all_islands_have_coords(self):
        self.assertEqual(len(AZORES_ISLANDS), 9)
        for island in AZORES_ISLANDS:
            self.assertTrue(-90 <= island['lat'] <= 90)
            self.assertTrue(-180 <= island['lng'] <= 180)
