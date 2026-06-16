"""Tests for unified entitlement resolution + legacy honoring + webhook."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from billing import services
from billing.models import Entitlement, Subscription

User = get_user_model()


class EntitlementServiceTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='u@x.com', email='u@x.com', password='x')

    def test_ensure_legacy_is_idempotent(self):
        Subscription.objects.create(email='u@x.com', is_active=True)
        services.ensure_legacy_entitlement(self.user)
        services.ensure_legacy_entitlement(self.user)
        self.assertEqual(self.user.entitlements.filter(source='legacy_email').count(), 1)
        self.assertEqual(services.resolve_entitlement(self.user).source, 'legacy_email')

    def test_revoke_returns_free(self):
        ent = Entitlement.objects.create(user=self.user, source='manual', tier='premium', status='active')
        self.assertIsNotNone(services.resolve_entitlement(self.user))
        ent.status = 'canceled'
        ent.save()
        self.assertIsNone(services.resolve_entitlement(self.user))

    def test_priority_paid_over_legacy(self):
        Entitlement.objects.create(user=self.user, source='legacy_email', tier='premium', status='active')
        Entitlement.objects.create(user=self.user, source='revenuecat', tier='premium', status='active', platform='ios')
        self.assertEqual(services.resolve_entitlement(self.user).source, 'revenuecat')

    def test_expired_period_excluded(self):
        Entitlement.objects.create(
            user=self.user, source='revenuecat', tier='premium', status='active',
            current_period_end=timezone.now() - timezone.timedelta(days=1),
        )
        self.assertIsNone(services.resolve_entitlement(self.user))

    def test_manage_via(self):
        legacy = Entitlement(source='legacy_email')
        stripe = Entitlement(source='stripe')
        rc_ios = Entitlement(source='revenuecat', platform='ios')
        rc_android = Entitlement(source='revenuecat', platform='android')
        self.assertEqual(services.manage_via(legacy), 'none')
        self.assertEqual(services.manage_via(stripe), 'stripe')
        self.assertEqual(services.manage_via(rc_ios), 'app_store')
        self.assertEqual(services.manage_via(rc_android), 'play_store')
        self.assertEqual(services.manage_via(None), 'none')

    def test_verify_subscription_lowercases(self):
        Subscription.objects.create(email='maria@example.com', is_active=True)
        result = services.verify_subscription(email='Maria@Example.com')
        self.assertTrue(result['hasActiveSubscription'])


class EntitlementEndpointTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='e@x.com', email='e@x.com', password='x')

    def test_legacy_premium_response(self):
        Subscription.objects.create(email='e@x.com', is_active=True)
        services.ensure_legacy_entitlement(self.user)
        self.client.force_authenticate(self.user)
        resp = self.client.get('/api/v3/billing/entitlement')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['tier'], 'premium')
        self.assertEqual(resp.data['source'], 'legacy_email')
        self.assertEqual(resp.data['manageVia'], 'none')

    def test_free_response_when_no_entitlement(self):
        self.client.force_authenticate(self.user)
        resp = self.client.get('/api/v3/billing/entitlement')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['tier'], 'free')

    def test_unauthenticated_rejected(self):
        self.assertEqual(self.client.get('/api/v3/billing/entitlement').status_code, 401)

    def test_compat_verify_mixed_case(self):
        Subscription.objects.create(email='compat@x.com', is_active=True)
        resp = self.client.post('/api/v1/subscription/verify/', {'email': 'Compat@X.com'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['hasActiveSubscription'])


@override_settings(REVENUECAT_WEBHOOK_SECRET='shh')
class RevenueCatWebhookTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='rc@x.com', email='rc@x.com', password='x')

    def test_signed_active_event_creates_entitlement(self):
        payload = {
            'event': {
                'type': 'INITIAL_PURCHASE',
                'app_user_id': str(self.user.id),
                'store': 'APP_STORE',
                'expiration_at_ms': int((timezone.now() + timezone.timedelta(days=30)).timestamp() * 1000),
            }
        }
        resp = self.client.post(
            '/api/v3/billing/webhooks/revenuecat',
            payload,
            format='json',
            HTTP_AUTHORIZATION='shh',
        )
        self.assertEqual(resp.status_code, 200)
        ent = services.resolve_entitlement(self.user)
        self.assertEqual(ent.source, 'revenuecat')
        self.assertEqual(services.manage_via(ent), 'app_store')

    def test_bad_secret_writes_nothing(self):
        resp = self.client.post(
            '/api/v3/billing/webhooks/revenuecat',
            {'event': {'app_user_id': str(self.user.id), 'type': 'INITIAL_PURCHASE'}},
            format='json',
            HTTP_AUTHORIZATION='wrong',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Entitlement.objects.count(), 0)

    def test_smb_user_prefix_app_user_id_creates_entitlement(self):
        payload = {
            'event': {
                'type': 'INITIAL_PURCHASE',
                'app_user_id': f'smb_user_{self.user.id}',
                'store': 'APP_STORE',
                'expiration_at_ms': int((timezone.now() + timezone.timedelta(days=30)).timestamp() * 1000),
            }
        }
        resp = self.client.post(
            '/api/v3/billing/webhooks/revenuecat',
            payload,
            format='json',
            HTTP_AUTHORIZATION='shh',
        )
        self.assertEqual(resp.status_code, 200)
        ent = services.resolve_entitlement(self.user)
        self.assertEqual(ent.source, 'revenuecat')
        self.assertEqual(ent.external_id, f'smb_user_{self.user.id}')

    def test_anonymous_app_user_id_is_ignored(self):
        resp = self.client.post(
            '/api/v3/billing/webhooks/revenuecat',
            {'event': {'app_user_id': '$RCAnonymousID:abc123', 'type': 'INITIAL_PURCHASE'}},
            format='json',
            HTTP_AUTHORIZATION='shh',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Entitlement.objects.count(), 0)

    def test_cancellation_marks_entitlement_canceled(self):
        services.reconcile_revenuecat(
            {
                'type': 'INITIAL_PURCHASE',
                'app_user_id': f'smb_user_{self.user.id}',
                'store': 'PLAY_STORE',
            }
        )
        services.reconcile_revenuecat(
            {
                'type': 'CANCELLATION',
                'app_user_id': f'smb_user_{self.user.id}',
                'store': 'PLAY_STORE',
            }
        )
        ent = Entitlement.objects.get(user=self.user, source='revenuecat')
        self.assertEqual(ent.status, 'canceled')
