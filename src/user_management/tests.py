"""Tests for the REST account/auth surface."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from billing.models import Subscription
from user_management.social import SocialIdentity, SocialVerificationError

User = get_user_model()

PW = 'Str0ngPass!23'


class RegisterLoginTests(APITestCase):
    def test_register_returns_token_and_me_lowercases_email(self):
        resp = self.client.post('/api/v3/auth/register', {'email': 'New@User.com', 'password': PW}, format='json')
        self.assertEqual(resp.status_code, 201)
        token = resp.data['token']
        self.assertTrue(token)
        self.assertEqual(resp.data['user']['email'], 'new@user.com')

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token}')
        me = self.client.get('/api/v3/auth/me')
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data['email'], 'new@user.com')

    def test_register_duplicate_mixed_case_is_rejected(self):
        self.client.post('/api/v3/auth/register', {'email': 'a@b.com', 'password': PW}, format='json')
        resp = self.client.post('/api/v3/auth/register', {'email': 'A@B.com', 'password': PW}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(User.objects.filter(email__iexact='a@b.com').count(), 1)

    def test_login_success_and_failure(self):
        self.client.post('/api/v3/auth/register', {'email': 'log@in.com', 'password': PW}, format='json')
        ok = self.client.post('/api/v3/auth/login', {'email': 'LOG@in.com', 'password': PW}, format='json')
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(ok.data['token'])

        bad = self.client.post('/api/v3/auth/login', {'email': 'log@in.com', 'password': 'wrong'}, format='json')
        self.assertEqual(bad.status_code, 401)

    def test_logout_invalidates_token(self):
        reg = self.client.post('/api/v3/auth/register', {'email': 'out@x.com', 'password': PW}, format='json')
        token = reg.data['token']
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token}')
        self.assertEqual(self.client.post('/api/v3/auth/logout').status_code, 200)
        self.assertEqual(self.client.get('/api/v3/auth/me').status_code, 401)

    def test_me_requires_auth(self):
        self.assertEqual(self.client.get('/api/v3/auth/me').status_code, 401)


class DeleteAccountTests(APITestCase):
    def _register(self, email='del@me.com'):
        reg = self.client.post(
            '/api/v3/auth/register', {'email': email, 'password': PW}, format='json'
        )
        return reg.data['token']

    def test_delete_requires_auth(self):
        self.assertEqual(self.client.delete('/api/v3/auth/account').status_code, 401)

    def test_delete_removes_user_token_and_entitlements(self):
        from rest_framework.authtoken.models import Token

        token = self._register('del@me.com')
        user = User.objects.get(email='del@me.com')
        # Legacy allow-list row + linked entitlement should also be purged.
        Subscription.objects.create(email='del@me.com', is_active=True)
        from billing.models import Entitlement

        Entitlement.objects.create(user=user, source=Entitlement.SOURCE_MANUAL)

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token}')
        resp = self.client.delete('/api/v3/auth/account')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['status'], 'deleted')

        self.assertFalse(User.objects.filter(email='del@me.com').exists())
        self.assertFalse(Token.objects.filter(key=token).exists())
        self.assertFalse(Entitlement.objects.filter(email='del@me.com').exists())
        self.assertFalse(Subscription.objects.filter(email__iexact='del@me.com').exists())

    def test_delete_invalidates_token(self):
        token = self._register('gone@me.com')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token}')
        self.assertEqual(self.client.delete('/api/v3/auth/account').status_code, 200)
        self.assertEqual(self.client.get('/api/v3/auth/me').status_code, 401)

    def test_delete_via_post_also_works(self):
        token = self._register('postdel@me.com')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token}')
        self.assertEqual(self.client.post('/api/v3/auth/account').status_code, 200)
        self.assertFalse(User.objects.filter(email='postdel@me.com').exists())


class SocialTests(APITestCase):
    def test_social_new_email_creates_user(self):
        identity = SocialIdentity(email='apple@user.com', name='Apple User', provider='apple')
        with patch('user_management.api_v3.verify_social_identity', return_value=identity):
            resp = self.client.post(
                '/api/v3/auth/social',
                {'provider': 'apple', 'identity_token': 'tok'},
                format='json',
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['user']['email'], 'apple@user.com')
        self.assertTrue(User.objects.filter(email='apple@user.com').exists())

    def test_social_links_existing_account(self):
        existing = User.objects.create_user(username='dup@user.com', email='dup@user.com', password=PW)
        identity = SocialIdentity(email='Dup@User.com', name='', provider='google')
        with patch('user_management.api_v3.verify_social_identity', return_value=identity):
            resp = self.client.post(
                '/api/v3/auth/social',
                {'provider': 'google', 'identity_token': 'tok'},
                format='json',
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(User.objects.filter(email__iexact='dup@user.com').count(), 1)
        self.assertEqual(resp.data['user']['id'], existing.id)

    def test_social_invalid_token_rejected(self):
        with patch(
            'user_management.api_v3.verify_social_identity',
            side_effect=SocialVerificationError('bad'),
        ):
            resp = self.client.post(
                '/api/v3/auth/social',
                {'provider': 'apple', 'identity_token': 'tok'},
                format='json',
            )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(User.objects.count(), 0)

    def test_social_honors_legacy_premium(self):
        Subscription.objects.create(email='legacy@user.com', is_active=True)
        identity = SocialIdentity(email='Legacy@User.com', provider='apple')
        with patch('user_management.api_v3.verify_social_identity', return_value=identity):
            self.client.post(
                '/api/v3/auth/social',
                {'provider': 'apple', 'identity_token': 'tok'},
                format='json',
            )
        user = User.objects.get(email='legacy@user.com')
        self.assertTrue(user.entitlements.filter(source='legacy_email', status='active').exists())
