"""Live stops resolve to OUR stops, by id, never by re-reading the name.

The temptation this file guards against is real and cheap-looking: `canonicalize`
is a pure function sitting in the same app, and running it over a live stage name
appears to work. It resolves about two thirds of stops, and for a handful of the
rest it produces a name that is wrong but entirely plausible -- which is worse
than a blank, because nothing downstream can tell it is wrong.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from django.core.cache import cache
from django.db import OperationalError
from django.test import TestCase, override_settings

from azoresbus.models import ExternalStop
from azoresbus.services_names import canonicalize
from azoresbus.services_stop_identity import (
    invalidate_stop_identity,
    safe_stop_identity_map,
    stop_identity_map,
)
from azoresbus.tracking_client import serialize_circulation, serialize_vehicle_detail
from tenancy.services import get_or_create_default_island
from transit.models import DATASET_AZORESBUS, Stop

LOC_MEM_CACHE = {
    'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
}
FIXTURE = (
    Path(__file__).resolve().parent / 'fixtures' / 'tracking_vehicle_detail.json'
)


def circulation(stage_id: str, name: str, sequence: int = 1) -> dict:
    return {
        'sequence': sequence,
        'stage': {
            'id': stage_id,
            'name': name,
            'nameShort': '4031',
            'position': {'lat': 37.76, 'lon': -25.31},
        },
        'departureTime': 33000,
        'arrivalTime': 33000,
        'dueInMinutes': 2,
    }


@override_settings(CACHES=LOC_MEM_CACHE)
class StopIdentityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.island = get_or_create_default_island()
        self.stop = Stop.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS,
            name='São Brás (Rua Tomé Vaz Pacheco)',
            cleaned_name='sao bras rua tome vaz pacheco',
            latitude=37.76, longitude=-25.31,
        )
        ExternalStop.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS,
            external_id='1250', code='5225',
            name='S. BRÁS (R. TOMÉ V. PACHECO)',
            latitude=37.76, longitude=-25.31, stop=self.stop,
        )

    def test_the_map_is_keyed_by_the_upstream_stage_id(self):
        identity = stop_identity_map(self.island)
        self.assertEqual(
            identity['1250'],
            {'stopId': self.stop.pk, 'name': 'São Brás (Rua Tomé Vaz Pacheco)'},
        )

    def test_the_id_join_beats_canonicalising_the_live_name(self):
        """The regression this whole approach exists for.

        Upstream abbreviates `Vaz` to `V.`, and the abbreviation table reads `V.`
        as `Vila` -- correct for most stops, wrong for this one. The schedules
        feed spells it out, so the importer never hits it; the live feed does not,
        so a live-side canonicalise always would.
        """
        live_name = 'S. BRÁS (R. TOMÉ V. PACHECO)'
        self.assertEqual(
            canonicalize(live_name), 'São Brás (Rua Tomé Vila Pacheco)',
            'if this changes, the trap moved -- do not just update the expectation',
        )

        row = serialize_circulation(
            circulation('1250', live_name), stop_identity_map(self.island),
        )
        self.assertEqual(row['stage']['canonicalName'], 'São Brás (Rua Tomé Vaz Pacheco)')
        self.assertEqual(row['stage']['stopId'], self.stop.pk)

    def test_the_operators_own_spelling_survives_alongside_ours(self):
        row = serialize_circulation(
            circulation('1250', 'S. BRÁS (R. TOMÉ V. PACHECO)'),
            stop_identity_map(self.island),
        )
        self.assertEqual(row['stage']['name'], 'S. BRÁS (R. TOMÉ V. PACHECO)')

    def test_an_unknown_stage_keeps_its_raw_name_rather_than_going_blank(self):
        """A stop added upstream since the last sync is still a real stop."""
        row = serialize_circulation(
            circulation('999999', 'RIBEIRINHA (AV. JOAQUIM MARIA CABRAL)'),
            stop_identity_map(self.island),
        )
        self.assertEqual(
            row['stage']['canonicalName'], 'RIBEIRINHA (AV. JOAQUIM MARIA CABRAL)',
        )
        self.assertIsNone(row['stage']['stopId'])

    def test_serialising_without_an_identity_map_is_the_raw_feed(self):
        row = serialize_circulation(circulation('1250', 'S. BRÁS'))
        self.assertEqual(row['stage']['canonicalName'], 'S. BRÁS')
        self.assertIsNone(row['stage']['stopId'])

    def test_a_broken_database_costs_names_not_the_vehicle(self):
        with patch(
            'azoresbus.services_stop_identity.stop_identity_map',
            side_effect=OperationalError('connection lost'),
        ):
            self.assertEqual(safe_stop_identity_map(self.island), {})

    def test_the_map_is_cached_and_invalidatable(self):
        stop_identity_map(self.island)
        ExternalStop.objects.all().delete()
        self.assertIn('1250', stop_identity_map(self.island), 'should still be cached')

        invalidate_stop_identity(self.island.key)
        self.assertEqual(stop_identity_map(self.island), {})


@override_settings(CACHES=LOC_MEM_CACHE)
class RealPayloadTests(TestCase):
    """Against the captured live vehicle, so the shape is the real one."""

    def setUp(self):
        cache.clear()
        self.island = get_or_create_default_island()
        self.raw = json.loads(FIXTURE.read_text())

    def test_every_circulation_gains_the_two_fields(self):
        payload = serialize_vehicle_detail(self.raw, {})
        circulations = payload['journey']['circulations']
        self.assertGreater(len(circulations), 50)
        for row in circulations:
            self.assertIn('canonicalName', row['stage'])
            self.assertIn('stopId', row['stage'])

    def test_resolution_is_per_stop_not_all_or_nothing(self):
        """A partially synced island shows real names where it can."""
        first = self.raw['journey']['circulations'][0]['stage']
        stop = Stop.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS,
            name='A Real Place', cleaned_name='a real place',
            latitude=37.7, longitude=-25.6,
        )
        identity = {str(first['id']): {'stopId': stop.pk, 'name': 'A Real Place'}}

        circulations = serialize_vehicle_detail(self.raw, identity)['journey']['circulations']
        resolved = [c for c in circulations if c['stage']['stopId'] is not None]
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]['stage']['canonicalName'], 'A Real Place')
        # ...and the rest still read as the operator wrote them.
        self.assertTrue(
            all(
                c['stage']['canonicalName'] == c['stage']['name']
                for c in circulations
                if c['stage']['stopId'] is None
            ),
        )
