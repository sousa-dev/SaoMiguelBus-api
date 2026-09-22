"""A new tenant's failure must not cost an existing one its scheduled refresh.

Island.Meta.ordering is by name, so adding the Madeira tenants put 'Madeira' *before*
'São Miguel' in every `for island in Island.objects.filter(...)` loop in the codebase.
Any such loop without a per-island guard turns a Madeira-only failure into a silent
outage for the shipped Azores product — and this one is beat-scheduled monthly.
"""
from unittest.mock import patch

from django.test import TestCase

from atlas.tasks import import_all_sources_task
from tenancy.models import Island

SEEN: list[str] = []


class Boom:
    """Stands in for every importer: fine everywhere except Madeira."""

    def __init__(self, island):
        self.island = island

    def run(self):
        SEEN.append(self.island.key)
        if self.island.key == 'madeira':
            raise RuntimeError('madeira extract is corrupt')
        return {'created': 0, 'updated': 1, 'tombstoned': 0}


class ImportAllSourcesIsolationTests(TestCase):
    def setUp(self):
        SEEN.clear()
        flags = {**Island.default_sao_miguel()['feature_flags'], 'atlas': True}
        for key, name in (('madeira', 'Madeira'), ('sao-miguel', 'São Miguel')):
            Island.objects.update_or_create(
                key=key,
                defaults={**Island.default_sao_miguel(), 'key': key, 'name': name,
                          'is_live': True, 'feature_flags': flags})
        self.assertLess('Madeira', 'São Miguel', 'ordering assumption')

    def test_one_islands_importer_failure_does_not_skip_the_others(self):
        registry = {s: Boom for s in ('transit', 'minibus', 'trails', 'curated', 'osm')}
        with patch('atlas.importers.IMPORTER_REGISTRY', registry):
            result = import_all_sources_task()

        self.assertIn('sao-miguel', SEEN, 'São Miguel must still be imported')
        self.assertIn('sao-miguel', result['islands'])
        self.assertIn('madeira', result.get('failed', {}))


class EnrichPoisIsolationTests(TestCase):
    """Same shared-fate risk, and this one runs daily."""

    def setUp(self):
        flags = {**Island.default_sao_miguel()['feature_flags'], 'atlas': True}
        for key, name in (('madeira', 'Madeira'), ('sao-miguel', 'São Miguel')):
            Island.objects.update_or_create(
                key=key,
                defaults={**Island.default_sao_miguel(), 'key': key, 'name': name,
                          'is_live': True, 'feature_flags': flags})

    def test_one_islands_provider_failure_does_not_skip_the_others(self):
        from atlas.models import AtlasCategory, AtlasPoi
        from atlas.tasks import enrich_pois_task

        for island in Island.objects.filter(key__in=('madeira', 'sao-miguel')):
            category, _ = AtlasCategory.objects.get_or_create(
                island=island, slug='places', defaults={'name': {'en': 'Places'}})
            AtlasPoi.objects.create(
                island=island, category=category, source_ref=f'{island.key}-1',
                name={'en': island.name}, latitude=island.center_lat,
                longitude=island.center_lng, is_active=True, tier=AtlasPoi.TIER_STANDARD)

        class Boom:
            model_name = 'test'

            def enrich(self, poi):
                if poi.island.key == 'madeira':
                    raise RuntimeError('provider refused')
                return None

        with patch('atlas.enrichment.load_provider', return_value=Boom()):
            result = enrich_pois_task()

        self.assertIn('sao-miguel', result['islands'])
        self.assertIn('madeira', result.get('failed', {}))
