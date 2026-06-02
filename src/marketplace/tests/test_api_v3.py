"""U3 API tests: CRUD verbs, ownership 403, tenant isolation, moderation, throttle."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from marketplace.models import Review, ServiceCategory, ServiceProvider
from tenancy.models import Island
from tenancy.services import get_or_create_default_island

SM = {'HTTP_X_ISLAND': 'sao-miguel'}


class MarketplaceAPITests(TestCase):
    def setUp(self):
        cache.clear()  # isolate throttle buckets between tests
        self.client = APIClient()
        self.island = get_or_create_default_island()
        self.category = ServiceCategory.objects.create(
            island=self.island, name='Electricians', slug='electricians'
        )
        self.staff = get_user_model().objects.create_user(
            username='staff', password='pw', is_staff=True
        )

    # --- helpers ------------------------------------------------------------

    def _create_provider(self, session='owner', name='Joana Electrics', **extra):
        body = {'session_id': session, 'name': name, 'category_slug': 'electricians', **extra}
        return self.client.post('/api/v3/marketplace/providers', body, format='json', **SM)

    def _publish(self, provider_id):
        self.client.force_authenticate(self.staff)
        resp = self.client.post(
            f'/api/v3/marketplace/providers/{provider_id}/moderate',
            {'action': 'publish'}, format='json', **SM,
        )
        self.client.force_authenticate(None)
        return resp

    # --- categories / list --------------------------------------------------

    def test_categories(self):
        resp = self.client.get('/api/v3/marketplace/categories', **SM)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['categories'][0]['slug'], 'electricians')

    def test_list_only_published_promoted_first(self):
        a = self._create_provider(session='a', name='Plain')
        b = self._create_provider(session='b', name='Promoted Co')
        self._publish(a.json()['id'])
        bid = b.json()['id']
        self._publish(bid)
        ServiceProvider.objects.filter(id=bid).update(is_promoted=True)
        names = [p['name'] for p in self.client.get('/api/v3/marketplace/providers', **SM).json()['providers']]
        self.assertEqual(names, ['Promoted Co', 'Plain'])

    # --- create / moderate --------------------------------------------------

    def test_create_provider_pending_not_public(self):
        resp = self._create_provider()
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['status'], 'pending')
        listed = self.client.get('/api/v3/marketplace/providers', **SM).json()['providers']
        self.assertEqual(listed, [])

    def test_moderate_requires_staff(self):
        pid = self._create_provider().json()['id']
        resp = self.client.post(
            f'/api/v3/marketplace/providers/{pid}/moderate', {'action': 'publish'}, format='json', **SM
        )
        self.assertEqual(resp.status_code, 403)

    def test_moderate_publishes(self):
        pid = self._create_provider().json()['id']
        self.assertEqual(self._publish(pid).status_code, 200)
        listed = self.client.get('/api/v3/marketplace/providers', **SM).json()['providers']
        self.assertEqual(len(listed), 1)

    def test_create_missing_session_id(self):
        resp = self.client.post(
            '/api/v3/marketplace/providers',
            {'name': 'X', 'category_slug': 'electricians'}, format='json', **SM,
        )
        self.assertEqual(resp.status_code, 400)

    def test_create_unknown_category(self):
        resp = self.client.post(
            '/api/v3/marketplace/providers',
            {'session_id': 's', 'name': 'X', 'category_slug': 'ghost'}, format='json', **SM,
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['error']['code'], 'invalid_category')

    # --- ownership ----------------------------------------------------------

    def test_patch_non_owner_forbidden(self):
        pid = self._create_provider(session='owner').json()['id']
        self._publish(pid)
        resp = self.client.patch(
            f'/api/v3/marketplace/providers/{pid}',
            {'session_id': 'intruder', 'name': 'Hijacked'}, format='json', **SM,
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()['error']['code'], 'not_owner')

    def test_patch_owner_reverts_to_pending(self):
        pid = self._create_provider(session='owner').json()['id']
        self._publish(pid)
        resp = self.client.patch(
            f'/api/v3/marketplace/providers/{pid}',
            {'session_id': 'owner', 'bio': 'updated'}, format='json', **SM,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'pending')

    def test_delete_soft_deletes(self):
        pid = self._create_provider(session='owner').json()['id']
        self._publish(pid)
        resp = self.client.delete(
            f'/api/v3/marketplace/providers/{pid}', **{**SM, 'HTTP_X_SESSION_ID': 'owner'}
        )
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(ServiceProvider.objects.get(id=pid).status, 'deleted')

    # --- tenant isolation ---------------------------------------------------

    def test_tenant_isolation(self):
        pid = self._create_provider().json()['id']
        self._publish(pid)
        Island.objects.create(key='terceira', name='Terceira', is_live=True)
        resp = self.client.get(
            f'/api/v3/marketplace/providers/{pid}', **{'HTTP_X_ISLAND': 'terceira'}
        )
        self.assertEqual(resp.status_code, 404)

    # --- reviews ------------------------------------------------------------

    def test_review_create_and_rating_after_publish(self):
        pid = self._create_provider().json()['id']
        self._publish(pid)
        resp = self.client.post(
            f'/api/v3/marketplace/providers/{pid}/reviews',
            {'session_id': 'rev', 'rating': 4, 'text': 'good'}, format='json', **SM,
        )
        self.assertEqual(resp.status_code, 201)
        review = Review.objects.get(provider_id=pid)
        self.client.force_authenticate(self.staff)
        self.client.post(
            f'/api/v3/marketplace/reviews/{review.id}/moderate', {'action': 'publish'}, format='json', **SM
        )
        self.client.force_authenticate(None)
        detail = self.client.get(f'/api/v3/marketplace/providers/{pid}', **SM).json()
        self.assertEqual(detail['rating'], 4.0)
        self.assertEqual(detail['reviewCount'], 1)

    def test_review_invalid_rating(self):
        pid = self._create_provider().json()['id']
        self._publish(pid)
        resp = self.client.post(
            f'/api/v3/marketplace/providers/{pid}/reviews',
            {'session_id': 'r', 'rating': 6}, format='json', **SM,
        )
        self.assertEqual(resp.status_code, 400)

    def test_review_upsert_single_row(self):
        pid = self._create_provider().json()['id']
        self._publish(pid)
        for rating in (5, 2):
            self.client.post(
                f'/api/v3/marketplace/providers/{pid}/reviews',
                {'session_id': 'same', 'rating': rating}, format='json', **SM,
            )
        self.assertEqual(Review.objects.filter(provider_id=pid).count(), 1)
        self.assertEqual(Review.objects.get(provider_id=pid).rating, 2)

    # --- throttle -----------------------------------------------------------

    def test_write_throttle(self):
        pid = self._create_provider().json()['id']
        self._publish(pid)
        cache.clear()
        last = None
        for i in range(22):
            last = self.client.post(
                f'/api/v3/marketplace/providers/{pid}/reviews',
                {'session_id': 'flooder', 'rating': 3}, format='json', **SM,
            )
        self.assertEqual(last.status_code, 429)
