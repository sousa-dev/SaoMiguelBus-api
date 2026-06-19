"""Mini Bus module tests."""

from pathlib import Path

from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from minibus.models import MinibusDocument, MinibusLine, MinibusTariff
from minibus.services import ATTRIBUTION, SOURCE_URL, combine_source_revisions, load_catalog, load_network_stops, seed_catalog
from tenancy.services import get_or_create_default_island

CATALOG_PATH = Path(__file__).resolve().parent.parent / 'data' / 'catalog_sao_miguel.json'


class CatalogTestCase(TestCase):
    def test_catalog_shape(self):
        catalog = load_catalog()
        self.assertEqual(len(catalog['lines']), 4)
        self.assertEqual(len(catalog['tariffs']), 8)
        self.assertEqual(len(catalog['documents']), 7)
        line_c = next(row for row in catalog['lines'] if row['code'] == 'C')
        self.assertEqual(
            line_c['service_summary']['saturday_departures'],
            ['09:00', '10:00', '11:00', '12:00', '13:00'],
        )

    def test_network_stops_shape(self):
        network = load_network_stops()
        self.assertEqual(len(network['lines']), 4)
        line_b = next(row for row in network['lines'] if row['code'] == 'B')
        self.assertEqual(line_b['stop_count'], 22)
        morgado = [s for s in line_b['stops'] if s['match_key'].startswith('rua-morgado-botelho')]
        self.assertEqual(len(morgado), 2)
        juventude = next(s for s in line_b['stops'] if 'Juventude' in s['name_pt'])
        self.assertEqual(juventude['name_pt'], 'Rua da Juventude')
        praca = next(s for s in line_b['stops'] if s['match_key'] == 'praca-vasco-da-gama')
        self.assertEqual(praca['interchange_lines'], ['C', 'D'])


class SeedCatalogTestCase(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()

    def test_seed_catalog_creates_rows(self):
        counts = seed_catalog(self.island)
        self.assertEqual(counts['lines'], 4)
        self.assertEqual(counts['tariffs'], 8)
        self.assertEqual(counts['documents'], 7)
        self.assertEqual(MinibusLine.objects.filter(island=self.island).count(), 4)
        self.assertEqual(MinibusTariff.objects.filter(island=self.island).count(), 8)


@override_settings(MEDIA_ROOT='/tmp/smb-minibus-test-media')
class ImportMinibusCommandTestCase(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        seed_catalog(self.island)

    def test_import_minibus_is_idempotent(self):
        source_dir = Path(__file__).resolve().parent.parent / 'data' / 'source'
        call_command('import_minibus', island='sao-miguel', source_dir=str(source_dir))
        call_command('import_minibus', island='sao-miguel', source_dir=str(source_dir))
        self.assertEqual(
            MinibusDocument.objects.filter(island=self.island).exclude(file='').count(),
            7,
        )
        from minibus.services import get_import_meta

        meta = get_import_meta(self.island)
        self.assertIsNotNone(meta)
        self.assertLessEqual(len(meta.source_revision), 64)

    def test_combine_source_revisions_fits_db_field(self):
        revisions = ['a' * 16, 'b' * 16, 'c' * 16, 'd' * 16, 'e' * 16, 'f' * 16, 'g' * 16]
        combined = combine_source_revisions(revisions)
        self.assertLessEqual(len(combined), 64)
        self.assertGreater(len(combined), 0)


class MinibusApiTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.island = get_or_create_default_island()
        flags = dict(self.island.feature_flags or {})
        flags['minibus'] = True
        self.island.feature_flags = flags
        self.island.save(update_fields=['feature_flags'])
        seed_catalog(self.island)
        source_dir = Path(__file__).resolve().parent.parent / 'data' / 'source'
        call_command('import_minibus', island='sao-miguel', source_dir=str(source_dir), skip_seed=True)

    def test_lines_list_without_header_uses_default_island(self):
        response = self.client.get('/api/v3/minibus/lines')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['lines']), 4)

    def test_lines_list(self):
        response = self.client.get('/api/v3/minibus/lines', HTTP_X_ISLAND='sao-miguel')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body['lines']), 4)
        self.assertEqual(body['source_url'], SOURCE_URL)
        self.assertEqual(body['attribution'], ATTRIBUTION)
        line_a = next(row for row in body['lines'] if row['code'] == 'A')
        self.assertTrue(line_a['timetable_file_url'].endswith('/api/v3/minibus/documents/line-a/file'))

    def test_document_file_stream(self):
        response = self.client.get(
            '/api/v3/minibus/documents/line-a/file',
            HTTP_X_ISLAND='sao-miguel',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('image/png', response['Content-Type'])

    def test_network_map_file_stream_is_png(self):
        response = self.client.get(
            '/api/v3/minibus/documents/network-map/file',
            HTTP_X_ISLAND='sao-miguel',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('image/png', response['Content-Type'])

    def test_document_file_stream_from_bundled_source_without_media(self):
        document = MinibusDocument.objects.get(island=self.island, slug='schematic')
        if document.file:
            document.file.delete(save=True)

        response = self.client.get(
            '/api/v3/minibus/documents/schematic/file',
            HTTP_X_ISLAND='sao-miguel',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('image/svg', response['Content-Type'])

        docs = self.client.get('/api/v3/minibus/documents', HTTP_X_ISLAND='sao-miguel')
        schematic = next(row for row in docs.json()['documents'] if row['slug'] == 'schematic')
        self.assertTrue(schematic['has_file'])
        self.assertTrue(schematic['file_url'].endswith('/api/v3/minibus/documents/schematic/file'))

    def test_bootstrap_includes_minibus_flag(self):
        response = self.client.get('/api/v3/bootstrap', HTTP_X_ISLAND='sao-miguel')
        self.assertEqual(response.status_code, 200)
        self.assertIn('minibus', response.json()['island']['enabledModules'])

    def test_tariffs_locale_pt(self):
        response = self.client.get(
            '/api/v3/minibus/tariffs?locale=pt',
            HTTP_X_ISLAND='sao-miguel',
        )
        self.assertEqual(response.status_code, 200)
        single = next(row for row in response.json()['tariffs'] if row['key'] == 'single_on_board')
        self.assertEqual(single['label'], 'Bilhete Simples (bordo)')

    def test_tariffs_locale_en(self):
        response = self.client.get(
            '/api/v3/minibus/tariffs?locale=en',
            HTTP_X_ISLAND='sao-miguel',
        )
        self.assertEqual(response.status_code, 200)
        single = next(row for row in response.json()['tariffs'] if row['key'] == 'single_on_board')
        self.assertEqual(single['label'], 'Single ticket (on board)')

    def test_lines_locale_pt_uses_portuguese_color_name(self):
        response = self.client.get(
            '/api/v3/minibus/lines?locale=pt',
            HTTP_X_ISLAND='sao-miguel',
        )
        self.assertEqual(response.status_code, 200)
        line_a = next(row for row in response.json()['lines'] if row['code'] == 'A')
        self.assertEqual(line_a['name'], 'Linha A — Amarela')

    def test_lines_locale_de_falls_back_to_english(self):
        response = self.client.get(
            '/api/v3/minibus/lines?locale=de',
            HTTP_X_ISLAND='sao-miguel',
        )
        self.assertEqual(response.status_code, 200)
        line_a = next(row for row in response.json()['lines'] if row['code'] == 'A')
        self.assertEqual(line_a['name'], 'Line A — Yellow')

    def test_network_stops_include_coordinates(self):
        response = self.client.get('/api/v3/minibus/network', HTTP_X_ISLAND='sao-miguel')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        line_a = next(line for line in body['lines'] if line['code'] == 'A')
        stop = next(s for s in line_a['stops'] if s['key'] == 'a-05')
        self.assertEqual(stop['external_id'], '105')
        self.assertAlmostEqual(stop['latitude'], 37.743677, places=5)
        self.assertAlmostEqual(stop['longitude'], -25.680908, places=5)

    def test_network_stops(self):
        response = self.client.get('/api/v3/minibus/network', HTTP_X_ISLAND='sao-miguel')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body['lines']), 4)
        line_a = next(row for row in body['lines'] if row['code'] == 'A')
        self.assertEqual(line_a['stop_count'], 21)
        self.assertEqual(line_a['color'], '#fbc707')
        monaco = next(s for s in line_a['stops'] if s['match_key'] == 'avenida-principe-do-monaco')
        self.assertEqual(monaco['interchange_lines'], ['D'])
        self.assertIn('centro-de-saude', body['interchanges_by_key'])
