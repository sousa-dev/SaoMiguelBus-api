"""Tests for ad selection platform filtering and the admin bulk retag action."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase
from django.utils import timezone

from tenancy.services import for_island
from transit.admin import AdAdmin
from transit.models import Ad, AdEvent
from transit.services.ads import get_ad_payload, record_ad_click, select_ad
from transit.tests.fixtures import ensure_transit_fixtures


class _DummyMessages:
    def __init__(self):
        self.messages = []

    def add(self, level, message, extra_tags=''):
        self.messages.append(message)


class SelectAdPlatformTests(TestCase):
    def setUp(self):
        self.island, _, _ = ensure_transit_fixtures()
        self.now = timezone.now()

    def _make_ad(self, *, platform: str, status: str = 'active', advertise_on: str = 'home') -> Ad:
        return Ad.objects.create(
            island=self.island,
            entity=f'{platform}-{status}',
            media='https://example.com/banner.png',
            start=self.now - timedelta(days=1),
            end=self.now + timedelta(days=1),
            advertise_on=advertise_on,
            platform=platform,
            status=status,
        )

    def test_platform_all_active_returned_for_ios(self):
        ad = self._make_ad(platform='all')
        with for_island(self.island):
            selected = select_ad(advertise_on='home', platform='ios')
        self.assertEqual(selected, ad)

    def test_platform_web_not_returned_for_ios(self):
        self._make_ad(platform='web')
        with for_island(self.island):
            selected = select_ad(advertise_on='home', platform='ios')
        self.assertIsNone(selected)

    def test_platform_web_default_fallback_for_ios(self):
        default = self._make_ad(platform='all', status='default')
        self._make_ad(platform='web')
        with for_island(self.island):
            selected = select_ad(advertise_on='home', platform='ios')
        self.assertEqual(selected, default)

    def test_ios_targeted_ad_returned_for_ios(self):
        ad = self._make_ad(platform='ios')
        with for_island(self.island):
            selected = select_ad(advertise_on='home', platform='ios')
        self.assertEqual(selected, ad)

    def test_interstitial_slot_matches_interstitial_campaign(self):
        ad = self._make_ad(platform='ios', advertise_on='interstitial')
        self._make_ad(platform='ios', advertise_on='home')
        with for_island(self.island):
            selected = select_ad(advertise_on='interstitial', platform='ios')
        self.assertEqual(selected, ad)

    def test_interstitial_slot_does_not_match_home_only_campaign(self):
        self._make_ad(platform='ios', advertise_on='home')
        with for_island(self.island):
            selected = select_ad(advertise_on='interstitial', platform='ios')
        self.assertIsNone(selected)


class AdEventEmissionTests(TestCase):
    def setUp(self):
        self.island, _, _ = ensure_transit_fixtures()
        self.now = timezone.now()
        self.ad = Ad.objects.create(
            island=self.island,
            entity='event-test',
            media='https://example.com/banner.png',
            start=self.now - timedelta(days=1),
            end=self.now + timedelta(days=1),
            advertise_on='home',
            platform='all',
            status='active',
        )

    def test_get_ad_payload_records_impression(self):
        with for_island(self.island):
            payload = get_ad_payload(advertise_on='home', platform='ios')
        self.assertIsNotNone(payload)
        event = AdEvent.objects.unscoped().get()
        self.assertEqual(event.kind, AdEvent.KIND_IMPRESSION)
        self.assertEqual(event.ad_id, self.ad.id)
        self.assertEqual(event.island_id, self.island.id)
        self.assertEqual(event.platform, 'ios')
        self.ad.refresh_from_db()
        self.assertEqual(self.ad.seen, 1)

    def test_impression_platform_all_stored_blank(self):
        with for_island(self.island):
            get_ad_payload(advertise_on='home', platform='all')
        event = AdEvent.objects.unscoped().get()
        self.assertEqual(event.platform, '')

    def test_record_ad_click_records_click_event(self):
        # Clicks arrive outside any island context (compat endpoint).
        self.assertTrue(record_ad_click(self.ad.id, platform='android'))
        event = AdEvent.objects.unscoped().get()
        self.assertEqual(event.kind, AdEvent.KIND_CLICK)
        self.assertEqual(event.island_id, self.island.id)
        self.assertEqual(event.platform, 'android')
        self.ad.refresh_from_db()
        self.assertEqual(self.ad.clicked, 1)

    def test_record_ad_click_missing_ad(self):
        self.assertFalse(record_ad_click(999999))
        self.assertEqual(AdEvent.objects.unscoped().count(), 0)


class AdAdminBulkActionTests(TestCase):
    def setUp(self):
        self.island, _, _ = ensure_transit_fixtures()
        self.now = timezone.now()
        self.admin = AdAdmin(Ad, AdminSite())
        self.factory = RequestFactory()

    def _make_ad(self, platform: str) -> Ad:
        return Ad.objects.create(
            island=self.island,
            entity=f'ad-{platform}',
            media='https://example.com/banner.png',
            start=self.now - timedelta(days=1),
            end=self.now + timedelta(days=1),
            advertise_on='home',
            platform=platform,
            status='active',
        )

    def test_set_platform_to_all_updates_selected(self):
        a = self._make_ad('web')
        b = self._make_ad('android')
        request = self.factory.post('/admin/')
        request._messages = _DummyMessages()

        queryset = Ad.objects.filter(id__in=[a.id, b.id])
        self.admin.set_platform_to_all(request, queryset)

        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(a.platform, 'all')
        self.assertEqual(b.platform, 'all')
        self.assertEqual(request._messages.messages, ['2 ads set to platform=all.'])
