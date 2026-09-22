from unittest.mock import patch
from django.test import TestCase
from tenancy.models import Island
from trails.models import Trail
from trails.services import sync_open_data_for_island


class MadeiraSyncTests(TestCase):
    def setUp(self):
        self.island, _ = Island.objects.get_or_create(
            key='madeira', defaults={**Island.default_sao_miguel(), 'key': 'madeira', 'archipelago': 'Madeira'})

    @patch('trails.services.fetch_dataset_geojson')
    @patch('trails.services.sync_visitazores_trails_for_island')
    def test_madeira_dispatch_avoids_azores_sources(self, azores_sync, azores_pois):
        with patch('trails.madeira_sync.sync_madeira_trails_for_island', return_value={'created': 1, 'updated': 0, 'skipped': 0}):
            result = sync_open_data_for_island(self.island)
        self.assertEqual(result['trails_created'], 1)
        azores_sync.assert_not_called()
        azores_pois.assert_not_called()

    @patch('trails.services.fetch_dataset_geojson')
    @patch('trails.services.sync_visitazores_trails_for_island')
    def test_removals_are_reported_not_silent(self, _azores_sync, _azores_pois):
        """Deleting rows is the one thing a sync does that cannot be undone by re-running."""
        with patch('trails.madeira_sync.sync_madeira_trails_for_island',
                   return_value={'created': 0, 'updated': 1, 'skipped': 0, 'removed': 2}):
            result = sync_open_data_for_island(self.island)
        self.assertEqual(result['trails_removed'], 2)

    def test_missing_geometry_preserves_existing_trail(self):
        trail = Trail.objects.create(island=self.island, source_ref='PR1', name='Existing')
        from trails.madeira_sync import sync_madeira_trails_for_island
        with patch('trails.madeira_sync._load_sources', return_value=(
            {'accessed': '2026-09-21', 'routes': [{'ref': 'PR1', 'name': 'PR1', 'island': 'madeira',
              'officialUrl': 'https://visitmadeira.com/pr1', 'statusAtImport': 'open', 'osmRelationId': 1}]},
            {})):
            result = sync_madeira_trails_for_island(self.island)
        self.assertEqual(result['skipped'], 1)
        trail.refresh_from_db()
        self.assertEqual(trail.name, 'Existing')

    def test_verified_geometry_creates_trail_with_official_facts(self):
        self.island.center_lat = 32.75
        self.island.center_lng = -16.98
        self.island.radius_km = 45
        self.island.save()
        from trails.madeira_sync import sync_madeira_trails_for_island
        geometry = {'type': 'LineString', 'coordinates': [
            [-16.9419, 32.7380], [-16.9400, 32.7420], [-16.9380, 32.7460]]}
        with patch('trails.madeira_sync._load_sources', return_value=(
            {'accessed': '2026-09-21', 'source': 'https://visitmadeira.com/x', 'routes': [
                {'ref': 'PR1', 'name': 'Vereda do Areeiro', 'island': 'madeira',
                 'officialUrl': 'https://visitmadeira.com/pr1', 'statusAtImport': 'closed',
                 'osmRelationIds': [2235102],
                 'official': {'distanceKm': 6.1, 'difficulty': 'Moderate', 'durationMin': 180}}]},
            {'PR1': geometry})):
            result = sync_madeira_trails_for_island(self.island)
        self.assertEqual(result['created'], 1)
        trail = Trail.objects.get(island=self.island, source_ref='PR1')
        self.assertEqual(trail.geojson, geometry)
        self.assertEqual(trail.leaflet_url, 'https://visitmadeira.com/pr1')
        self.assertEqual(trail.distance_km, 6.1)
        self.assertIn('closed', trail.description_en)
        self.assertIn('2026-09-21', trail.description_en)

    def test_geometry_outside_island_bounds_is_rejected(self):
        self.island.center_lat = 32.75
        self.island.center_lng = -16.98
        self.island.radius_km = 45
        self.island.save()
        from trails.madeira_sync import sync_madeira_trails_for_island
        with patch('trails.madeira_sync._load_sources', return_value=(
            {'accessed': '2026-09-21', 'routes': [
                {'ref': 'PR1', 'name': 'Vereda do Areeiro', 'island': 'madeira',
                 'officialUrl': 'https://visitmadeira.com/pr1', 'statusAtImport': 'open',
                 'osmRelationId': 2235102}]},
            {'PR1': {'type': 'LineString', 'coordinates': [
                [-25.49, 37.78], [-25.48, 37.79]]}})):
            result = sync_madeira_trails_for_island(self.island)
        self.assertEqual(result['skipped'], 1)
        self.assertFalse(Trail.objects.filter(island=self.island, source_ref='PR1').exists())

    def test_routes_of_another_area_are_not_imported(self):
        from trails.madeira_sync import sync_madeira_trails_for_island
        with patch('trails.madeira_sync._load_sources', return_value=(
            {'accessed': '2026-09-21', 'routes': [
                {'ref': 'PR1', 'name': 'Vereda do Pico Branco', 'island': 'porto-santo',
                 'officialUrl': 'https://visitmadeira.com/ps1', 'statusAtImport': 'open'}]},
            {})):
            result = sync_madeira_trails_for_island(self.island)
        self.assertEqual(result['created'], 0)
        self.assertFalse(Trail.objects.filter(island=self.island).exists())

    def test_attribution_for_madeira_credits_visit_madeira_and_osm(self):
        from tenancy.services import for_island
        from trails.services import trails_attribution
        with for_island(self.island):
            attribution = trails_attribution()
        self.assertIn('Visit Madeira', attribution)
        self.assertIn('OpenStreetMap', attribution)
        self.assertNotIn('Visit Azores', attribution)

    def _madeira_island(self):
        self.island.center_lat = 32.75
        self.island.center_lng = -16.98
        self.island.radius_km = 45
        self.island.save()
        return self.island

    def test_official_distance_is_preferred_over_the_measured_track(self):
        """Visit Madeira publishes the route's distance; our OSM line is only an approximation.

        PR1 is published as 6.1 km while the matched OSM relation measures 5.33 km. Showing
        the measured number presents our approximation as the official fact.
        """
        island = self._madeira_island()
        from trails.madeira_sync import sync_madeira_trails_for_island
        geometry = {'type': 'LineString', 'coordinates': [[-16.90, 32.75], [-16.90, 32.76]]}
        with patch('trails.madeira_sync._load_sources', return_value=(
            {'accessed': '2026-09-21', 'routes': [
                {'ref': 'PR1', 'name': 'Vereda', 'island': 'madeira',
                 'officialUrl': 'https://visitmadeira.com/pr1', 'statusAtImport': 'open',
                 'osmRelationIds': [1],
                 'official': {'distanceKm': 6.1, 'difficulty': 'Moderate', 'durationMin': 180}}]},
            {'PR1': geometry})):
            sync_madeira_trails_for_island(island)
        trail = Trail.objects.get(island=island, source_ref='PR1')
        self.assertEqual(trail.distance_km, 6.1)
        self.assertEqual(trail.duration_min, 180)
        self.assertEqual(trail.difficulty, 'moderate')

    def test_the_published_start_and_end_appear_in_the_description(self):
        """Where a route starts and ends is the first thing a hiker needs offline."""
        island = self._madeira_island()
        from trails.madeira_sync import sync_madeira_trails_for_island
        geometry = {'type': 'LineString', 'coordinates': [[-16.90, 32.75], [-16.90, 32.76]]}
        with patch('trails.madeira_sync._load_sources', return_value=(
            {'accessed': '2026-09-21', 'routes': [
                {'ref': 'PR1', 'name': 'Vereda', 'island': 'madeira',
                 'officialUrl': 'https://visitmadeira.com/pr1', 'statusAtImport': 'open',
                 'osmRelationIds': [1],
                 'official': {'distanceKm': 6.1,
                              'startEnd': 'Pico do Areeiro Viewpoint / Pico Ruivo'}}]},
            {'PR1': geometry})):
            sync_madeira_trails_for_island(island)
        trail = Trail.objects.get(island=island, source_ref='PR1')
        self.assertIn('Pico do Areeiro Viewpoint / Pico Ruivo', trail.description_en)
        self.assertIn('Pico do Areeiro Viewpoint / Pico Ruivo', trail.description_pt)

    def test_without_an_official_distance_none_is_claimed(self):
        """Rather than publish the length of our own approximation as the route's distance."""
        island = self._madeira_island()
        from trails.madeira_sync import sync_madeira_trails_for_island
        geometry = {'type': 'LineString', 'coordinates': [[-16.90, 32.75], [-16.90, 32.76]]}
        with patch('trails.madeira_sync._load_sources', return_value=(
            {'accessed': '2026-09-21', 'routes': [
                {'ref': 'PR1', 'name': 'Vereda', 'island': 'madeira',
                 'officialUrl': 'https://visitmadeira.com/pr1', 'statusAtImport': 'open',
                 'osmRelationIds': [1]}]},
            {'PR1': geometry})):
            sync_madeira_trails_for_island(island)
        trail = Trail.objects.get(island=island, source_ref='PR1')
        self.assertIsNone(trail.distance_km)

    def test_a_multi_segment_track_is_never_measured_into_a_distance(self):
        """The shipped line is an approximation; only Visit Madeira states the distance.

        An OSM route relation is dozens of separate ways, and measuring across the gaps
        between them read a Madeira PR as tens of kilometres longer than it is. Rather than
        fix that sum, the distance now comes from the publisher or not at all.
        """
        island = self._madeira_island()
        from trails.madeira_sync import sync_madeira_trails_for_island
        geometry = {'type': 'MultiLineString', 'coordinates': [
            [[-16.90, 32.75], [-16.90, 32.76]],
            [[-16.80, 32.75], [-16.80, 32.76]]]}
        with patch('trails.madeira_sync._load_sources', return_value=(
            {'accessed': '2026-09-21', 'routes': [
                {'ref': 'PR1', 'name': 'Vereda', 'island': 'madeira',
                 'officialUrl': 'https://visitmadeira.com/pr1', 'statusAtImport': 'open',
                 'osmRelationIds': [1]}]},
            {'PR1': geometry})):
            sync_madeira_trails_for_island(island)
        trail = Trail.objects.get(island=island, source_ref='PR1')
        self.assertIsNone(trail.distance_km)

    def test_multi_variant_route_reports_no_single_distance(self):
        island = self._madeira_island()
        from trails.madeira_sync import sync_madeira_trails_for_island
        geometry = {'type': 'MultiLineString', 'coordinates': [
            [[-16.90, 32.75], [-16.90, 32.76]],
            [[-16.80, 32.75], [-16.80, 32.76]]]}
        with patch('trails.madeira_sync._load_sources', return_value=(
            {'accessed': '2026-09-21', 'routes': [
                {'ref': 'PR2', 'name': 'Vereda', 'island': 'madeira',
                 'officialUrl': 'https://visitmadeira.com/pr2', 'statusAtImport': 'open',
                 'osmRelationIds': [1, 2]}]},
            {'PR2': geometry})):
            sync_madeira_trails_for_island(island)
        trail = Trail.objects.get(island=island, source_ref='PR2')
        self.assertIsNone(trail.distance_km)
        self.assertIn('variant', trail.description_en)

    def test_a_route_withdrawn_from_the_official_list_is_removed(self):
        island = self._madeira_island()
        Trail.objects.create(island=island, source_ref='PR99', name='Retired route')
        from trails.madeira_sync import sync_madeira_trails_for_island
        geometry = {'type': 'LineString', 'coordinates': [[-16.90, 32.75], [-16.90, 32.76]]}
        with patch('trails.madeira_sync._load_sources', return_value=(
            {'accessed': '2026-09-21', 'routes': [
                {'ref': 'PR1', 'name': 'Vereda', 'island': 'madeira',
                 'officialUrl': 'https://visitmadeira.com/pr1', 'statusAtImport': 'open',
                 'osmRelationIds': [1]}]},
            {'PR1': geometry})):
            result = sync_madeira_trails_for_island(island)
        self.assertEqual(result['removed'], 1)
        self.assertFalse(Trail.objects.filter(island=island, source_ref='PR99').exists())
        self.assertTrue(Trail.objects.filter(island=island, source_ref='PR1').exists())

    def test_a_route_still_listed_but_lacking_geometry_is_never_removed(self):
        island = self._madeira_island()
        Trail.objects.create(island=island, source_ref='PR1', name='Existing')
        from trails.madeira_sync import sync_madeira_trails_for_island
        with patch('trails.madeira_sync._load_sources', return_value=(
            {'accessed': '2026-09-21', 'routes': [
                {'ref': 'PR1', 'name': 'Vereda', 'island': 'madeira',
                 'officialUrl': 'https://visitmadeira.com/pr1', 'statusAtImport': 'open',
                 'osmRelationIds': [1]}]},
            {})):
            result = sync_madeira_trails_for_island(island)
        self.assertEqual(result['removed'], 0)
        self.assertEqual(result['skipped'], 1)
        self.assertTrue(Trail.objects.filter(island=island, source_ref='PR1').exists())

    def test_an_unreadable_manifest_removes_nothing(self):
        """A missing or corrupt source file must never empty the catalogue."""
        island = self._madeira_island()
        Trail.objects.create(island=island, source_ref='PR1', name='Existing')
        from trails.madeira_sync import sync_madeira_trails_for_island
        with patch('trails.madeira_sync._load_sources', return_value=({}, {})):
            result = sync_madeira_trails_for_island(island)
        self.assertEqual(result['removed'], 0)
        self.assertTrue(Trail.objects.filter(island=island, source_ref='PR1').exists())



class MadeiraShippedDataTests(TestCase):
    """Guard the snapshotted files the offline bundle is built from."""

    def _island(self, key, lat, lng, radius):
        # The tenancy seed migration already created these four; assert its geography.
        island = Island.objects.get(key=key)
        self.assertEqual(island.archipelago, 'Madeira')
        self.assertEqual((island.center_lat, island.center_lng, island.radius_km),
                         (lat, lng, radius))
        return island

    def test_every_official_route_imports_with_verified_geometry(self):
        from trails.madeira_sync import _load_sources, sync_madeira_trails_for_island
        _load_sources.cache_clear()
        madeira = self._island('madeira', 32.75, -16.98, 45)
        porto_santo = self._island('porto-santo', 33.06, -16.34, 13)

        counts = {k: sync_madeira_trails_for_island(v)
                  for k, v in (('madeira', madeira), ('porto-santo', porto_santo))}
        self.assertEqual(counts['madeira']['skipped'], 0)
        self.assertEqual(counts['porto-santo']['skipped'], 0)
        self.assertEqual(counts['madeira']['created'], 37)
        self.assertEqual(counts['porto-santo']['created'], 3)

        for trail in Trail.objects.all():
            self.assertTrue(trail.geojson.get('coordinates'), trail.source_ref)
            self.assertIn('visitmadeira.com', trail.leaflet_url, trail.source_ref)
            self.assertIn('Access can change', trail.description_en, trail.source_ref)
            if trail.distance_km is not None:
                self.assertGreater(trail.distance_km, 0.3, trail.source_ref)
                self.assertLess(trail.distance_km, 30.0, trail.source_ref)

    def test_shipped_routes_never_claim_an_unverified_status(self):
        from trails.madeira_sync import STATUS_LABELS_EN, _load_sources
        _load_sources.cache_clear()
        manifest, geometry = _load_sources()
        self.assertTrue(manifest['accessed'])
        for route in manifest['routes']:
            self.assertIn(route['statusAtImport'], STATUS_LABELS_EN, route['ref'])
            self.assertIn(route['island'], {'madeira', 'porto-santo', 'desertas', 'selvagens'})
            self.assertIn(route['ref'], geometry, route['ref'])
