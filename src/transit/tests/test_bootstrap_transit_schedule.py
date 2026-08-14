"""00 Decision 1: the app renders the cutover, it does not compute it.

`transitSchedule` states which dataset is active, whether preview is offered,
what the banner says and when it retires. A build installed in June is correct
in September because it never had the decision to make.

`nextTransitionAt` exists specifically to defuse the stale-cache problem: the app
persists bootstrap for 24h and `useBootstrapCached` never refetches, so without
an instant to invalidate at it has no way to know its copy became a lie
(98 §4 gap "Stale bootstrap").
"""

from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch

from django.test import TestCase

from tenancy.bootstrap import serialize_bootstrap
from tenancy.services import get_or_create_default_island
from transit.models import DATASET_AZORESBUS, DATASET_LEGACY, Line, Operator, Trip


CUTOVER = '2026-09-01T00:00:00+00:00'
BANNER_UNTIL = '2026-10-01T00:00:00+00:00'


class TransitScheduleTests(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        self.island.feature_flags = {
            **(self.island.feature_flags or {}),
            'azoresbus': {
                'cutoverAt': CUTOVER,
                'bannerUntil': BANNER_UNTIL,
                'previewEnabled': True,
                'trackingEnabled': False,
                'banner': {
                    'id': 'azoresbus-live-2026-09',
                    'tone': 'info',
                    'dismissible': False,
                    'text': {'pt': 'Novos horários', 'en': 'New timetables'},
                },
                'badge': {
                    'text': {'pt': 'Válido desde 1 de setembro',
                             'en': 'Valid since 1 September'},
                },
            },
        }
        self.island.save(update_fields=['feature_flags'])
        operator, _ = Operator.objects.get_or_create(
            island=self.island, name='AzoresBus', defaults={'contact': {}},
        )
        line = Line.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, code='101',
            operator=operator,
        )
        Trip.objects.create(
            island=self.island, dataset=DATASET_AZORESBUS, line=line,
            source=Trip.SOURCE_OPERATOR,
        )

    def _at(self, iso: str) -> dict:
        moment = datetime.fromisoformat(iso).replace(tzinfo=dt_timezone.utc)
        with patch('transit.services.schedule_phase.timezone.now',
                   return_value=moment):
            return serialize_bootstrap(self.island)['transitSchedule']

    # -- presence and shape --------------------------------------------------

    def test_the_block_is_present(self):
        block = self._at('2026-08-20T10:00')
        for key in (
            'activeDataset', 'previewDataset', 'cutoverAt',
            'nextTransitionAt', 'phase', 'banner', 'badge', 'trackingEnabled',
        ):
            self.assertIn(key, block)

    def test_instants_are_serialised_as_instants_not_dates(self):
        block = self._at('2026-08-20T10:00')
        self.assertIn('T', block['cutoverAt'])
        self.assertTrue(
            block['cutoverAt'].endswith('+00:00')
            or block['cutoverAt'].endswith('Z'),
            'cutoverAt must carry an offset or the client cannot compare it',
        )

    # -- phases --------------------------------------------------------------

    def test_preview_phase_before_cutover(self):
        block = self._at('2026-08-20T10:00')
        self.assertEqual(block['phase'], 'preview')
        self.assertEqual(block['activeDataset'], DATASET_LEGACY)
        self.assertEqual(block['previewDataset'], DATASET_AZORESBUS)

    def test_live_phase_after_cutover(self):
        block = self._at('2026-09-15T10:00')
        self.assertEqual(block['phase'], 'live')
        self.assertEqual(block['activeDataset'], DATASET_AZORESBUS)
        self.assertIsNone(
            block['previewDataset'],
            'there is nothing left to preview once it is live',
        )

    def test_settled_phase_after_the_banner_retires(self):
        block = self._at('2026-10-15T10:00')
        self.assertEqual(block['phase'], 'settled')
        self.assertEqual(block['activeDataset'], DATASET_AZORESBUS)

    # -- nextTransitionAt ----------------------------------------------------

    def test_next_transition_is_the_cutover_while_previewing(self):
        self.assertEqual(
            self._at('2026-08-20T10:00')['nextTransitionAt'][:10], '2026-09-01',
        )

    def test_next_transition_is_the_banner_end_while_live(self):
        self.assertEqual(
            self._at('2026-09-15T10:00')['nextTransitionAt'][:10], '2026-10-01',
        )

    def test_next_transition_is_null_once_settled(self):
        self.assertIsNone(self._at('2026-10-15T10:00')['nextTransitionAt'])

    # -- flags ---------------------------------------------------------------

    def test_preview_can_be_switched_off_without_a_release(self):
        self.island.feature_flags['azoresbus']['previewEnabled'] = False
        self.island.save(update_fields=['feature_flags'])
        self.assertIsNone(self._at('2026-08-20T10:00')['previewDataset'])

    def test_banner_and_badge_copy_come_from_flags(self):
        block = self._at('2026-09-15T10:00')
        self.assertEqual(block['banner']['text']['pt'], 'Novos horários')
        self.assertEqual(
            block['badge']['text']['en'], 'Valid since 1 September',
        )

    def test_tracking_is_reported_and_off(self):
        self.assertFalse(self._at('2026-09-15T10:00')['trackingEnabled'])


class UnconfiguredIslandTests(TestCase):
    def test_an_island_with_no_azoresbus_block_degrades_gracefully(self):
        """The app must behave exactly as today against an un-migrated API."""
        island = get_or_create_default_island()
        island.feature_flags = {'transit': True}
        island.save(update_fields=['feature_flags'])

        block = serialize_bootstrap(island)['transitSchedule']
        self.assertIsNone(block['cutoverAt'])
        self.assertEqual(block['activeDataset'], DATASET_LEGACY)
        self.assertEqual(block['phase'], 'preview')
        self.assertIsNone(block['previewDataset'])
