"""Mini Bus coordinate merge tests."""

import json
from pathlib import Path

from django.test import SimpleTestCase

from minibus.data.merge_coordinates import (
    apply_coordinates,
    load_network_stops,
    load_stops_registry,
    registry_coordinate_index,
    validate_network_coordinates,
    write_merged_network,
)


class CoordinateMergeTestCase(SimpleTestCase):
  @classmethod
  def setUpClass(cls):
    super().setUpClass()
    cls.registry = load_stops_registry()
    cls.network = load_network_stops()

  def test_all_routable_stops_have_coordinates(self):
    merged = apply_coordinates(self.network, self.registry)
    errors = validate_network_coordinates(merged)
    self.assertEqual(errors, [], msg='\n'.join(errors))

  def test_a05_maps_from_registry_id_105(self):
    merged = apply_coordinates(self.network, self.registry)
    line_a = next(line for line in merged['lines'] if line['code'] == 'A')
    stop = next(s for s in line_a['stops'] if s['key'] == 'a-05')
    self.assertEqual(stop['external_id'], '105')
    self.assertAlmostEqual(stop['latitude'], 37.743677, places=5)
    self.assertAlmostEqual(stop['longitude'], -25.680908, places=5)

  def test_loop_stop_a21_inherits_a01_coordinates(self):
    merged = apply_coordinates(self.network, self.registry)
    line_a = next(line for line in merged['lines'] if line['code'] == 'A')
    first = next(s for s in line_a['stops'] if s['key'] == 'a-01')
    last = next(s for s in line_a['stops'] if s['key'] == 'a-21')
    self.assertEqual(last['latitude'], first['latitude'])
    self.assertEqual(last['longitude'], first['longitude'])

  def test_d03_prefers_santa_clara_not_eng_abel(self):
    index = registry_coordinate_index(self.registry)
    row = index[('D', 3)]
    self.assertEqual(str(row['id']), '403')

  def test_nd_hospital_rows_map_to_d12_d13(self):
    merged = apply_coordinates(self.network, self.registry)
    line_d = next(line for line in merged['lines'] if line['code'] == 'D')
    d12 = next(s for s in line_d['stops'] if s['key'] == 'd-12')
    d13 = next(s for s in line_d['stops'] if s['key'] == 'd-13')
    self.assertEqual(d12['external_id'], '412')
    self.assertEqual(d13['external_id'], '413')
    self.assertIsNotNone(d12['latitude'])
    self.assertIsNotNone(d13['latitude'])

  def test_merged_network_file_on_disk_is_valid(self):
    errors = validate_network_coordinates(self.network)
    self.assertEqual(errors, [])


class CoordinateRegistryTestCase(SimpleTestCase):
  def test_registry_file_exists(self):
    path = Path(__file__).resolve().parent.parent / 'data' / 'stops_registry_sao_miguel.json'
    self.assertTrue(path.is_file())
    rows = json.loads(path.read_text(encoding='utf-8'))
    self.assertEqual(len(rows), 90)
