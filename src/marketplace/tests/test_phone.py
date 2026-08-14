"""Phone normalization and provider phone fix."""

from __future__ import annotations

from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from marketplace import services
from marketplace.models import ServiceCategory, ServiceProvider
from marketplace.phone import normalize_pt_phone
from src import settings as project_settings
from tenancy.services import get_or_create_default_island


class NormalizePtPhoneTests(TestCase):
    def test_empty(self):
        self.assertEqual(normalize_pt_phone(''), '')
        self.assertEqual(normalize_pt_phone(None), '')
        self.assertEqual(normalize_pt_phone('   '), '')

    def test_already_correct(self):
        self.assertEqual(normalize_pt_phone('+351912345678'), '+351912345678')

    def test_nine_digit_national(self):
        self.assertEqual(normalize_pt_phone('912345678'), '+351912345678')

    def test_leading_zero(self):
        self.assertEqual(normalize_pt_phone('0912345678'), '+351912345678')

    def test_country_code_without_plus(self):
        self.assertEqual(normalize_pt_phone('351912345678'), '+351912345678')

    def test_international_00_prefix(self):
        self.assertEqual(normalize_pt_phone('00351912345678'), '+351912345678')

    def test_spaces_and_punctuation(self):
        self.assertEqual(normalize_pt_phone('+351 912 345 678'), '+351912345678')
        self.assertEqual(normalize_pt_phone('(91) 234-5678'), '+351912345678')

    def test_country_code_with_trunk_zero(self):
        self.assertEqual(normalize_pt_phone('3510912345678'), '+351912345678')

    def test_unparseable(self):
        self.assertIsNone(normalize_pt_phone('123'))
        self.assertIsNone(normalize_pt_phone('not-a-phone'))


class FixProviderPhoneNumbersTests(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        # marketplace/0002 seeds eight default categories for sao-miguel.
        # It only ever looked like a no-op because the migration graph used
        # to order it BEFORE the island existed; these fixtures build their
        # own categories and must not depend on that accident.
        ServiceCategory.objects.filter(island=self.island).delete()
        self.category = ServiceCategory.objects.create(
            island=self.island, name='Other', slug='other', is_active=True
        )

    def _provider(self, **fields) -> ServiceProvider:
        return ServiceProvider.objects.create(
            island=self.island,
            category=self.category,
            name='Test Provider',
            status=ServiceProvider.PUBLISHED,
            **fields,
        )

    def test_fixes_phone_and_whatsapp(self):
        provider = self._provider(phone='912345678', whatsapp='0911111111')
        result = services.fix_provider_phone_numbers(dry_run=False)
        provider.refresh_from_db()
        self.assertEqual(result['updated'], 1)
        self.assertEqual(provider.phone, '+351912345678')
        self.assertEqual(provider.whatsapp, '+351911111111')

    def test_dry_run_does_not_save(self):
        provider = self._provider(phone='912345678', whatsapp='')
        services.fix_provider_phone_numbers(dry_run=True)
        provider.refresh_from_db()
        self.assertEqual(provider.phone, '912345678')

    def test_leaves_valid_numbers_unchanged(self):
        provider = self._provider(phone='+351912345678', whatsapp='+351911111111')
        result = services.fix_provider_phone_numbers(dry_run=False)
        provider.refresh_from_db()
        self.assertEqual(result['updated'], 0)
        self.assertEqual(provider.phone, '+351912345678')


@override_settings(AUTH_KEY='test-auth-key')
class FixProviderPhonesOpsTests(TestCase):
    def setUp(self):
        self.auth_patcher = patch.object(project_settings, 'AUTHENTICATION_REQUIRED', False)
        self.auth_patcher.start()
        self.addCleanup(self.auth_patcher.stop)
        self.client = APIClient()
        self.url = '/api/v1/ops/marketplace/fix-phones'
        self.island = get_or_create_default_island()
        # marketplace/0002 seeds eight default categories for sao-miguel.
        # It only ever looked like a no-op because the migration graph used
        # to order it BEFORE the island existed; these fixtures build their
        # own categories and must not depend on that accident.
        ServiceCategory.objects.filter(island=self.island).delete()
        self.category = ServiceCategory.objects.create(
            island=self.island, name='Other', slug='other', is_active=True
        )
        ServiceProvider.objects.create(
            island=self.island,
            category=self.category,
            name='Ops Provider',
            phone='912345678',
            whatsapp='351911111111',
            status=ServiceProvider.PUBLISHED,
        )

    def test_requires_auth_key(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)

    def test_fixes_via_get_endpoint(self):
        response = self.client.get(f'{self.url}?key={settings.AUTH_KEY}')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['ok'])
        self.assertEqual(body['updated'], 1)
        provider = ServiceProvider.objects.get(name='Ops Provider')
        self.assertEqual(provider.phone, '+351912345678')
        self.assertEqual(provider.whatsapp, '+351911111111')
