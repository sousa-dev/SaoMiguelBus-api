"""Village-level search: "Capelas -> Ponta Delgada" without naming a landmark.

`search_routes` unions every stop sharing a village's name prefix when the
query matches that village exactly (folded) and no real stop's own exact name
collides with it (`azoresbus/services_stops.py:build_area_index`). AzoresBus
only -- legacy has no `NAME (LANDMARK)` convention, so `area_index` is `None`
there and the path is never touched.

Fixture design note, deliberately followed here: the trip under test serves
`CAPELAS (MOAGEM)`, NOT `CAPELAS (ESCOLA)` -- which sorts first alphabetically
by `cleaned_name`. If the area branch silently failed to fire (the exact bug a
design review caught: an unfolded index key never matching a folded query) the
OLD `cleaned_name__startswith` fallback would still resolve "capelas" to
whichever Capelas stop sorts first and could accidentally pass a test built
around that one -- for the wrong reason. Serving a non-alphabetically-first
member makes that failure mode visible instead of silently masked.
"""

from __future__ import annotations

from datetime import time

from django.test import TestCase
from rest_framework.test import APIClient

from tenancy.services import get_or_create_default_island
from transit.models import (
    DATASET_AZORESBUS,
    DATASET_LEGACY,
    Line,
    Operator,
    ServicePattern,
    Stop,
    StopTime,
    Trip,
)

HEADERS = {'HTTP_X_ISLAND': 'sao-miguel'}


class AreaSearchFixture(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.island = get_or_create_default_island()
        self.operator, _ = Operator.objects.get_or_create(
            island=self.island, name='AzoresBus', defaults={'contact': {}},
        )
        self.pattern = ServicePattern.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, key='everyday',
            monday=True, tuesday=True, wednesday=True, thursday=True,
            friday=True, saturday=True, sunday=True,
        )
        # eligible_trips() filters on Trip.service regardless of dataset --
        # legacy trips need a ServicePattern too, not a Calendar (that backfill
        # path is tested elsewhere; a direct pattern is simpler here).
        self.legacy_pattern = ServicePattern.objects.create(
            island=self.island, dataset=DATASET_LEGACY, key='everyday',
            monday=True, tuesday=True, wednesday=True, thursday=True,
            friday=True, saturday=True, sunday=True,
        )
        self._line_seq = 0

    def _stop(self, name: str, dataset: str = DATASET_AZORESBUS) -> Stop:
        return Stop.objects.create(
            island=self.island, dataset=dataset, name=name,
            cleaned_name=name.lower(), latitude=37.7, longitude=-25.6,
        )

    def _trip(self, stops: list[tuple[Stop, str]], dataset: str = DATASET_AZORESBUS) -> Trip:
        """stops: (Stop, 'HH:MM')."""
        self._line_seq += 1
        line = Line.objects.create(
            island=self.island, dataset=dataset, code=f'L{self._line_seq}',
            operator=self.operator,
        )
        pattern = self.pattern if dataset == DATASET_AZORESBUS else self.legacy_pattern
        trip = Trip.objects.create(
            island=self.island, dataset=dataset, line=line,
            service=pattern, source=Trip.SOURCE_OPERATOR,
        )
        for index, (stop, hhmm) in enumerate(stops, start=1):
            hour, minute = (int(part) for part in hhmm.split(':'))
            StopTime.objects.create(
                island=self.island, trip=trip, stop=stop, sequence=index,
                departure_time=time(hour, minute), day_offset=0,
            )
        return trip

    def _search(self, origin: str, destination: str, dataset: str | None = None) -> list[dict]:
        params = {'origin': origin, 'destination': destination,
                  'day': 'weekday', 'start': '00h00'}
        if dataset:
            params['dataset'] = dataset
        response = self.client.get('/api/v3/transit/search', params, **HEADERS)
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response.json()['results']


class AreaUnionTests(AreaSearchFixture):
    def setUp(self):
        super().setUp()
        self.escola = self._stop('CAPELAS (ESCOLA)')   # sorts FIRST alphabetically
        self.igreja = self._stop('CAPELAS (IGREJA)')
        self.moagem = self._stop('CAPELAS (MOAGEM)')    # deliberately NOT first -- see module docstring
        self.arrifes = self._stop('ARRIFES (ESCOLA)')
        self.destination = self._stop('PONTA DELGADA (ALFÂNDEGA)')

    def test_a_trip_serving_only_one_non_first_member_is_found(self):
        self._trip([(self.moagem, '07:00'), (self.destination, '07:30')])

        results = self._search('Capelas', 'Ponta Delgada', dataset=DATASET_AZORESBUS)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['start'], '07h00')

    def test_a_trip_outside_the_area_is_not_returned(self):
        self._trip([(self.arrifes, '07:00'), (self.destination, '07:30')])

        results = self._search('Capelas', 'Ponta Delgada', dataset=DATASET_AZORESBUS)

        self.assertEqual(results, [])

    def test_a_trip_can_be_found_via_any_member_independently(self):
        self._trip([(self.escola, '06:00'), (self.destination, '06:30')])
        self._trip([(self.igreja, '08:00'), (self.destination, '08:30')])
        self._trip([(self.moagem, '10:00'), (self.destination, '10:30')])

        results = self._search('Capelas', 'Ponta Delgada', dataset=DATASET_AZORESBUS)

        self.assertEqual(sorted(r['start'] for r in results), ['06h00', '08h00', '10h00'])

    def test_an_intra_village_hop_is_a_valid_search(self):
        """Capelas -> Capelas: a real local ride between two different member
        stops. Board precedes alight is the whole rule (matches the existing
        loop philosophy, see matcher.py's ALFA->ALFA test)."""
        self._trip([(self.escola, '07:00'), (self.arrifes, '07:15'), (self.moagem, '07:30')])

        results = self._search('Capelas', 'Capelas', dataset=DATASET_AZORESBUS)

        self.assertEqual(len(results), 1)
        self.assertEqual((results[0]['start'], results[0]['end']), ('07h00', '07h30'))


class CollisionExclusionEndToEndTests(AreaSearchFixture):
    """AFLITOS-shaped: a real bare stop plus several prefixed siblings. Exact
    match must win, never the union -- there is no way to distinguish the two
    from the query string alone."""

    def setUp(self):
        super().setUp()
        self.bare = self._stop('AFLITOS')
        self.aflitos_a = self._stop('AFLITOS (ESCOLA)')
        self.aflitos_b = self._stop('AFLITOS (IGREJA)')
        self.destination = self._stop('PONTA DELGADA (ALFÂNDEGA)')

    def test_the_bare_stop_alone_is_matched_not_the_union(self):
        on_bare = self._trip([(self.bare, '07:00'), (self.destination, '07:30')])
        self._trip([(self.aflitos_a, '09:00'), (self.destination, '09:30')])

        results = self._search('Aflitos', 'Ponta Delgada', dataset=DATASET_AZORESBUS)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], on_bare.id)


class LegacyDatasetUnaffectedTests(AreaSearchFixture):
    """dataset=legacy must never consult the area index, even defensively --
    not just because real legacy names never contain '(', but because the gate
    in search_routes is an explicit `dataset == DATASET_AZORESBUS` check."""

    def test_a_legacy_stop_shaped_like_an_area_member_is_not_unioned(self):
        # A legacy stop that WOULD look area-shaped if the gate were missing.
        legacy_a = self._stop('CAPELAS (NAVIO)', dataset=DATASET_LEGACY)
        legacy_b = self._stop('CAPELAS (ROSSIO)', dataset=DATASET_LEGACY)
        destination = self._stop('PONTA DELGADA', dataset=DATASET_LEGACY)
        self._trip([(legacy_a, '07:00'), (destination, '07:30')], dataset=DATASET_LEGACY)

        results = self._search('Capelas', 'Ponta Delgada', dataset=DATASET_LEGACY)

        # No stop named exactly "Capelas" and no area index on legacy: the
        # startswith fallback resolves to ONE of the two, not a union of both.
        self.assertLessEqual(len(results), 1)

    def test_legacy_real_bare_capelas_stop_resolves_as_a_single_stop(self):
        bare = self._stop('Capelas', dataset=DATASET_LEGACY)
        destination = self._stop('Ponta Delgada', dataset=DATASET_LEGACY)
        self._trip([(bare, '07:00'), (destination, '07:30')], dataset=DATASET_LEGACY)

        results = self._search('Capelas', 'Ponta Delgada', dataset=DATASET_LEGACY)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['start'], '07h00')
