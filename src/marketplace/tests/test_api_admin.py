"""Superuser admin API tests for marketplace moderation queues."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from marketplace.models import Review, ServiceCategory, ServiceProvider
from tenancy.services import get_or_create_default_island

SM = {'HTTP_X_ISLAND': 'sao-miguel'}


class MarketplaceAdminAPITests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.island = get_or_create_default_island()
        # marketplace/0002 seeds eight default categories for sao-miguel.
        # It only ever looked like a no-op because the migration graph used
        # to order it BEFORE the island existed; these fixtures build their
        # own categories and must not depend on that accident.
        ServiceCategory.objects.filter(island=self.island).delete()
        self.category = ServiceCategory.objects.create(
            island=self.island, name='Electricians', slug='electricians', is_active=True
        )
        ServiceCategory.objects.create(
            island=self.island, name='Other', slug='other', is_active=True
        )
        self.superuser = get_user_model().objects.create_superuser(
            username='admin@x.com', email='admin@x.com', password='pw'
        )
        self.regular = get_user_model().objects.create_user(
            username='user@x.com', email='user@x.com', password='pw'
        )
        self.staff_only = get_user_model().objects.create_user(
            username='staff@x.com', email='staff@x.com', password='pw', is_staff=True
        )
        self.provider = ServiceProvider.objects.create(
            island=self.island,
            category=self.category,
            name='Pending Co',
            bio='Test bio',
            phone='+351910000000',
            status=ServiceProvider.PENDING,
            created_by_session_hash='hash-a',
        )
        self.review = Review.objects.create(
            island=self.island,
            provider=self.provider,
            rating=4,
            text='Nice work',
            status=Review.PENDING,
            created_by_session_hash='hash-b',
        )
        self.suggested = ServiceCategory.objects.create(
            island=self.island,
            name='New Cat',
            slug='new-cat',
            user_suggested=True,
        )

    def test_queue_requires_auth(self):
        self.assertEqual(
            self.client.get('/api/v3/marketplace/admin/queue', **SM).status_code,
            401,
        )

    def test_queue_forbidden_for_regular_user(self):
        self.client.force_authenticate(self.regular)
        self.assertEqual(
            self.client.get('/api/v3/marketplace/admin/queue', **SM).status_code,
            403,
        )

    def test_queue_forbidden_for_staff_non_superuser(self):
        self.client.force_authenticate(self.staff_only)
        self.assertEqual(
            self.client.get('/api/v3/marketplace/admin/queue', **SM).status_code,
            403,
        )

    def test_queue_summary_for_superuser(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.get('/api/v3/marketplace/admin/queue', **SM)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['pendingProviders'], 1)
        self.assertEqual(data['pendingReviews'], 1)
        self.assertEqual(data['suggestedCategories'], 1)

    def test_list_pending_providers(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.get('/api/v3/marketplace/admin/providers', **SM)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body['total'], 1)
        self.assertEqual(body['providers'][0]['name'], 'Pending Co')
        self.assertEqual(body['providers'][0]['status'], 'pending')

    def test_list_pending_reviews_includes_provider_name(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.get('/api/v3/marketplace/admin/reviews', **SM)
        self.assertEqual(resp.status_code, 200)
        review = resp.json()['reviews'][0]
        self.assertEqual(review['providerName'], 'Pending Co')

    def test_list_suggested_categories(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.get('/api/v3/marketplace/admin/categories', **SM)
        self.assertEqual(resp.status_code, 200)
        slugs = [c['slug'] for c in resp.json()['categories']]
        self.assertEqual(slugs, ['new-cat'])

    def test_moderate_provider_publish(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.post(
            f'/api/v3/marketplace/admin/providers/{self.provider.id}/moderate',
            {'action': 'publish'},
            format='json',
            **SM,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'published')

    def test_admin_patch_provider_promoted(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.patch(
            f'/api/v3/marketplace/admin/providers/{self.provider.id}',
            {'is_promoted': True, 'status': 'published'},
            format='json',
            **SM,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body['isPromoted'])
        self.assertEqual(body['status'], 'published')

    def test_admin_patch_review(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.patch(
            f'/api/v3/marketplace/admin/reviews/{self.review.id}',
            {'rating': 5, 'text': 'Updated'},
            format='json',
            **SM,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['rating'], 5)
        self.assertEqual(resp.json()['text'], 'Updated')

    def test_admin_approve_category(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.patch(
            f'/api/v3/marketplace/admin/categories/{self.suggested.id}',
            {'name': 'Renamed Cat', 'approve': True},
            format='json',
            **SM,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body['name'], 'Renamed Cat')
        self.assertFalse(body['userSuggested'])
        self.assertTrue(body['isActive'])

    def test_admin_category_slug_conflict(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.patch(
            f'/api/v3/marketplace/admin/categories/{self.suggested.id}',
            {'slug': 'electricians'},
            format='json',
            **SM,
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['error']['code'], 'slug_conflict')

    def test_pagination_limit_offset(self):
        for i in range(3):
            ServiceProvider.objects.create(
                island=self.island,
                category=self.category,
                name=f'Extra {i}',
                bio='Bio',
                phone='+351910000001',
                status=ServiceProvider.PENDING,
                created_by_session_hash=f'hash-{i}',
            )
        self.client.force_authenticate(self.superuser)
        resp = self.client.get('/api/v3/marketplace/admin/providers?limit=2&offset=1', **SM)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body['limit'], 2)
        self.assertEqual(body['offset'], 1)
        self.assertEqual(body['total'], 4)
        self.assertEqual(len(body['providers']), 2)
