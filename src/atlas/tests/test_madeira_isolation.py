from django.test import TestCase
from rest_framework.test import APIClient

from atlas.models import AtlasCategory, AtlasPoi
from atlas.services import publish
from tenancy.models import Island
from tenancy.services import get_or_create_default_island


class MadeiraIsolationTests(TestCase):
    def setUp(self):
        self.azores = get_or_create_default_island()
        self.madeira, _ = Island.objects.get_or_create(
            key='madeira',
            defaults={**Island.default_sao_miguel(), 'key': 'madeira', 'name': 'Madeira', 'archipelago': 'Madeira'},
        )
        for island in (self.azores, self.madeira):
            category = AtlasCategory.objects.create(island=island, slug='places', name={'en': 'Places'}, revision=1)
            poi = AtlasPoi.objects.create(island=island, category=category, source_ref=island.key,
                                          name={'en': island.name}, latitude=island.center_lat,
                                          longitude=island.center_lng)
            publish(poi)

    def test_stats_are_scoped_by_archipelago_and_default_to_azores(self):
        client = APIClient()
        self.assertEqual(client.get('/api/v3/atlas/stats').json()['pois'], 1)
        self.assertEqual(client.get('/api/v3/atlas/stats?archipelago=madeira').json()['pois'], 1)
        self.assertEqual(client.get('/api/v3/atlas/stats?archipelago=madeira').json()['islands'], 1)
        self.assertEqual(client.get('/api/v3/atlas/stats?archipelago=madeira', HTTP_X_ISLAND='sao-miguel').status_code, 400)
        self.assertEqual(client.get('/api/v3/atlas/stats?archipelago=other').status_code, 400)

    def test_unknown_explicit_island_is_rejected(self):
        client = APIClient()
        for path in ('/api/v3/atlas/sync', '/api/v3/atlas/stats', '/api/v3/trails/', '/api/v3/weather/parishes'):
            response = client.get(path, HTTP_X_ISLAND='not-an-island')
            self.assertEqual(response.status_code, 400, path)

    def test_a_valid_madeira_island_is_not_rejected(self):
        """The strict check must reject unknown keys, not every explicit key."""
        client = APIClient()
        response = client.get('/api/v3/atlas/sync', HTTP_X_ISLAND='madeira')
        self.assertNotEqual(response.status_code, 400, response.content)

    def test_a_blank_island_header_falls_back_instead_of_400ing(self):
        """A blank header is no more explicit than no header at all.

        Sending `X-Island: ' '` used to reach the strict check as an empty key and be
        refused as `Unknown island: `, which named nothing and told the caller nothing.
        """
        client = APIClient()
        response = client.get('/api/v3/atlas/stats', HTTP_X_ISLAND='   ')
        self.assertEqual(response.status_code, 200, response.content)

    def test_case_and_whitespace_in_an_island_header_still_resolve(self):
        client = APIClient()
        response = client.get('/api/v3/atlas/sync', HTTP_X_ISLAND='  Madeira  ')
        self.assertNotEqual(response.status_code, 400, response.content)
