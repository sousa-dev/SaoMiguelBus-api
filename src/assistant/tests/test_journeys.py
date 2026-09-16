"""Tests for `GET /api/v3/ai/journeys`."""

from __future__ import annotations

from django.test import TestCase
from django.core.cache import cache
from unittest.mock import patch
from rest_framework.test import APIClient

from tenancy.services import for_island
from transit.models import DATASET_AZORESBUS, ServicePattern
from transit.tests.fixtures import ensure_transit_fixtures
from transit.tests.test_search_areas import AreaSearchFixture

# 2026-09-15 is a Tuesday (weekday) -- picked to match the plan brief's own
# worked example ("Tue 15 Sep 2026") and to keep the test deterministic
# regardless of what day it actually runs on.
WEEKDAY_DATE = '2026-09-15'


class AIJourneysTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.island, self.trip, self.line = ensure_transit_fixtures()
        # Date-resolved searches require a ServicePattern. The shared fixture
        # only creates a legacy Calendar for day-type searches.
        with for_island(self.island):
            service, _ = ServicePattern.objects.get_or_create(
                island=self.island, key='assistant-test-weekdays',
                defaults={day: True for day in ServicePattern.WEEKDAY_FIELDS[:5]},
            )
            self.trip.service = service
            self.trip.save(update_fields=['service'])

    def test_known_pair_returns_journeys_summary_and_deep_link(self):
        response = self.client.get(
            '/api/v3/ai/journeys',
            {
                'from': 'Ponta Delgada',
                'to': 'Ribeira Grande',
                'date': WEEKDAY_DATE,
                'time': '00:00',
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(body['resolved'], {'from': 'Ponta Delgada', 'to': 'Ribeira Grande'})
        self.assertEqual(body['query']['date'], WEEKDAY_DATE)
        self.assertEqual(body['query']['dayType'], 'weekday')
        self.assertEqual(body['suggestions'], {})

        self.assertEqual(len(body['journeys']), 1)
        journey = body['journeys'][0]
        self.assertEqual(journey['start'], '08h30')
        self.assertEqual(journey['end'], '09h15')
        self.assertEqual(journey['transfers'], 0)

        self.assertIn('Ponta Delgada', body['summary'])
        self.assertIn('Ribeira Grande', body['summary'])
        self.assertIn('08:30', body['summary'])
        self.assertIn('direct', body['summary'])

        self.assertEqual(
            body['links']['web'],
            'https://saomiguelbus.com/transit?origin=Ponta%20Delgada&destination=Ribeira%20Grande',
        )
        self.assertIn('/api/v3/ai/journeys', body['links']['api'])
        self.assertIn('saomiguelbus.com', body['attribution'])
        self.assertIn('generatedAt', body)

    def test_typo_returns_no_journeys_but_suggestions(self):
        response = self.client.get(
            '/api/v3/ai/journeys',
            {'from': 'Ponta Delgadaz', 'to': 'Ribeira Grande', 'date': WEEKDAY_DATE},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(body['journeys'], [])
        self.assertIsNone(body['resolved']['from'])
        self.assertEqual(body['resolved']['to'], 'Ribeira Grande')
        self.assertIn('Could not identify', body['summary'])
        self.assertIn('from', body['suggestions'])
        names = [item['name'] for item in body['suggestions']['from']]
        self.assertIn('Ponta Delgada', names)

    def test_unresolved_destination_english_word_returns_suggestions_not_a_guess(self):
        response = self.client.get(
            '/api/v3/ai/journeys',
            {'from': 'Ponta Delgada', 'to': 'Nowhere Imaginary', 'date': WEEKDAY_DATE},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(body['journeys'], [])
        self.assertIsNone(body['resolved']['to'])
        self.assertIn('to', body['suggestions'])

    def test_date_tomorrow_resolves_to_a_real_date(self):
        response = self.client.get(
            '/api/v3/ai/journeys',
            {'from': 'Ponta Delgada', 'to': 'Ribeira Grande', 'date': 'tomorrow'},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertRegex(body['query']['date'], r'^\d{4}-\d{2}-\d{2}$')
        self.assertNotEqual(body['query']['date'], 'tomorrow')

    def test_date_today_default(self):
        response = self.client.get(
            '/api/v3/ai/journeys', {'from': 'Ponta Delgada', 'to': 'Ribeira Grande'},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertRegex(body['query']['date'], r'^\d{4}-\d{2}-\d{2}$')

    def test_format_md_returns_markdown_content_type(self):
        response = self.client.get(
            '/api/v3/ai/journeys',
            {
                'from': 'Ponta Delgada',
                'to': 'Ribeira Grande',
                'date': WEEKDAY_DATE,
                'time': '00:00',
                'format': 'md',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/markdown; charset=utf-8')
        self.assertTrue(response.content.startswith(b'# Buses:'), response.content[:80])
        self.assertIn(b'\n\n', response.content)
        self.assertNotIn(b'\\n', response.content)
        body = response.content.decode()
        self.assertIn('Ponta Delgada', body)
        self.assertIn('Ribeira Grande', body)
        self.assertIn('saomiguelbus.com', body)

    def test_accept_header_text_markdown_also_selects_markdown(self):
        response = self.client.get(
            '/api/v3/ai/journeys',
            {'from': 'Ponta Delgada', 'to': 'Ribeira Grande', 'date': WEEKDAY_DATE},
            HTTP_ACCEPT='text/markdown',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/markdown; charset=utf-8')
        self.assertTrue(response.content.startswith(b'# Buses:'), response.content[:80])

    def test_format_md_overrides_json_accept_header(self):
        response = self.client.get(
            '/api/v3/ai/journeys',
            {'from': 'Ponta Delgada', 'to': 'Ribeira Grande',
             'date': WEEKDAY_DATE, 'time': '00:00', 'format': 'md'},
            HTTP_ACCEPT='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/markdown; charset=utf-8')
        self.assertTrue(response.content.startswith(b'# Buses:'), response.content[:80])
        self.assertIn(b'\n\n', response.content)

    def test_lang_pt_summary_is_portuguese(self):
        response = self.client.get(
            '/api/v3/ai/journeys',
            {
                'from': 'Ponta Delgada',
                'to': 'Ribeira Grande',
                'date': WEEKDAY_DATE,
                'time': '00:00',
                'lang': 'pt',
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn('Próximos autocarros', body['summary'])
        self.assertIn('direto', body['summary'])

    def test_missing_params_returns_400(self):
        response = self.client.get('/api/v3/ai/journeys', {'from': 'Ponta Delgada'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], 'invalid_params')

    def test_invalid_date_and_time_return_400_instead_of_using_today_or_now(self):
        params = {'from': 'Ponta Delgada', 'to': 'Ribeira Grande'}
        for invalid in ('weekday', '2026-02-30', 'tomorow'):
            with self.subTest(date=invalid):
                response = self.client.get('/api/v3/ai/journeys', {**params, 'date': invalid})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()['error']['code'], 'invalid_params')
        response = self.client.get('/api/v3/ai/journeys', {**params, 'time': '25:99'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], 'invalid_params')
        markdown_error = self.client.get(
            '/api/v3/ai/journeys', {**params, 'date': 'weekday'},
            HTTP_ACCEPT='text/markdown',
        )
        self.assertEqual(markdown_error.status_code, 400)
        self.assertIn('invalid_params', markdown_error.content.decode())

    def test_limit_is_clamped_to_max_ten(self):
        response = self.client.get(
            '/api/v3/ai/journeys',
            {
                'from': 'Ponta Delgada',
                'to': 'Ribeira Grande',
                'date': WEEKDAY_DATE,
                'limit': '999',
            },
        )
        self.assertEqual(response.status_code, 200)
        # Only one trip exists in fixtures; this just proves the request
        # doesn't error/reject an out-of-range limit.
        self.assertLessEqual(len(response.json()['journeys']), 10)

    def test_ai_throttle_scope_is_registered(self):
        from django.conf import settings

        self.assertEqual(settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['ai'], '120/min')

    def test_repeated_query_reuses_cached_answer(self):
        from assistant.services import build_ai_journeys

        params = {
            'from': 'Ponta Delgada', 'to': 'Ribeira Grande',
            'date': WEEKDAY_DATE, 'time': '00:00',
        }
        with patch('assistant.api_v3.build_ai_journeys', wraps=build_ai_journeys) as build:
            first = self.client.get('/api/v3/ai/journeys', params)
            second = self.client.get('/api/v3/ai/journeys', params)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(build.call_count, 1)

    def test_resolve_dataset_never_receives_a_client_supplied_requested(self):
        """A `dataset=legacy` query param must never flip the active network --
        that kwarg is admin/preview-only (schedule_phase.resolve_dataset docstring)."""
        response = self.client.get(
            '/api/v3/ai/journeys',
            {
                'from': 'Ponta Delgada',
                'to': 'Ribeira Grande',
                'date': WEEKDAY_DATE,
                'dataset': 'azoresbus',
                'time': '00:00',
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        # The fixture trip only exists on the legacy dataset; if `dataset` were
        # honoured from the query string this would silently search an empty
        # (or different) network instead.
        self.assertEqual(len(body['journeys']), 1)


class AIAreaJourneyTestCase(AreaSearchFixture):
    def test_area_query_keeps_union_for_non_first_stop(self):
        self._stop('CAPELAS (ESCOLA)')
        self._stop('CAPELAS (IGREJA)')
        moagem = self._stop('CAPELAS (MOAGEM)')
        destination = self._stop('PONTA DELGADA')
        self._trip([(moagem, '07:00'), (destination, '07:30')])

        with patch('assistant.services.resolve_dataset', return_value=DATASET_AZORESBUS):
            response = self.client.get('/api/v3/ai/journeys', {
                'from': 'Capelas', 'to': 'Ponta Delgada',
                'date': WEEKDAY_DATE, 'time': '00:00',
            })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body['journeys']), 1)
        self.assertEqual(body['journeys'][0]['start'], '07h00')
        self.assertEqual(body['resolved']['from'], 'CAPELAS')
        self.assertIn('CAPELAS', body['summary'])
        self.assertNotIn('ESCOLA', body['summary'])

    def test_destination_area_keeps_union_for_non_first_stop(self):
        self._stop('CAPELAS (ESCOLA)')
        self._stop('CAPELAS (IGREJA)')
        moagem = self._stop('CAPELAS (MOAGEM)')
        origin = self._stop('PONTA DELGADA')
        self._trip([(origin, '07:00'), (moagem, '07:30')])

        with patch('assistant.services.resolve_dataset', return_value=DATASET_AZORESBUS):
            response = self.client.get('/api/v3/ai/journeys', {
                'from': 'Ponta Delgada', 'to': 'Capelas',
                'date': WEEKDAY_DATE, 'time': '00:00',
            })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body['journeys']), 1)
        self.assertEqual(body['journeys'][0]['end'], '07h30')
        self.assertEqual(body['resolved']['to'], 'CAPELAS')
