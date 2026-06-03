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
        ServiceCategory.objects.create(
            island=self.island, name='Other', slug='other'
        )
        self.staff = get_user_model().objects.create_user(
            username='staff', password='pw', is_staff=True
        )

    # --- helpers ------------------------------------------------------------

    def _create_provider(self, session='owner', name='Joana Electrics', **extra):
        body = {
            'session_id': session,
            'name': name,
            'category_slug': 'electricians',
            'bio': 'Licensed electrician on São Miguel.',
            'phone': '+351910000000',
            **extra,
        }
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
            {
                'session_id': 's',
                'name': 'X',
                'category_slug': 'ghost',
                'bio': 'Desc',
                'phone': '123',
            },
            format='json',
            **SM,
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['error']['code'], 'invalid_category')

    def test_create_with_category_name(self):
        resp = self.client.post(
            '/api/v3/marketplace/providers',
            {
                'session_id': 'owner',
                'name': 'Rex Walks',
                'category_name': 'Dog Walking',
                'bio': 'Daily dog walks in Ponta Delgada.',
                'email': 'rex@example.com',
            },
            format='json',
            **SM,
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['category']['slug'], 'dog-walking')
        cats = self.client.get('/api/v3/marketplace/categories', **SM).json()['categories']
        slugs = [c['slug'] for c in cats]
        self.assertIn('dog-walking', slugs)
        cat = next(c for c in cats if c['slug'] == 'dog-walking')
        self.assertTrue(cat['userSuggested'])

    def test_create_rejects_both_category_fields(self):
        resp = self.client.post(
            '/api/v3/marketplace/providers',
            {
                'session_id': 's',
                'name': 'X',
                'category_slug': 'electricians',
                'category_name': 'Other',
            },
            format='json',
            **SM,
        )
        self.assertEqual(resp.status_code, 400)

    def test_create_rejects_invalid_category_name(self):
        resp = self.client.post(
            '/api/v3/marketplace/providers',
            {
                'session_id': 's',
                'name': 'X',
                'category_name': '!!',
                'bio': 'Desc',
                'phone': '123',
            },
            format='json',
            **SM,
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['error']['code'], 'invalid_category_name')

    def test_create_without_category_defaults_to_other(self):
        resp = self.client.post(
            '/api/v3/marketplace/providers',
            {
                'session_id': 'owner',
                'name': 'Generic Help',
                'bio': 'Handyman services.',
                'whatsapp': '+351910000001',
            },
            format='json',
            **SM,
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['category']['slug'], 'other')

    def test_create_requires_bio(self):
        resp = self.client.post(
            '/api/v3/marketplace/providers',
            {
                'session_id': 's',
                'name': 'X',
                'category_slug': 'electricians',
                'phone': '123',
            },
            format='json',
            **SM,
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['error']['code'], 'bio_required')

    def test_create_requires_contact(self):
        resp = self.client.post(
            '/api/v3/marketplace/providers',
            {
                'session_id': 's',
                'name': 'X',
                'category_slug': 'electricians',
                'bio': 'Some work.',
            },
            format='json',
            **SM,
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['error']['code'], 'contact_required')

    def test_create_without_hourly_rate(self):
        resp = self._create_provider(hourly_rate=None)
        self.assertEqual(resp.status_code, 201)
        self.assertIsNone(resp.json().get('hourlyRate'))

    def test_create_claimed_owner_with_internal_email(self):
        resp = self._create_provider(
            claimed_owner=True,
            internal_email='owner@example.com',
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertTrue(body['claimedOwner'])
        self.assertEqual(body['internalEmail'], 'owner@example.com')
        self.assertFalse(body['verifiedByOwner'])

    def test_create_claimed_owner_requires_internal_contact(self):
        resp = self._create_provider(claimed_owner=True)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['error']['code'], 'owner_contact_required')

    def test_create_claimed_owner_false_omits_internal_fields(self):
        resp = self._create_provider(claimed_owner=False)
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertFalse(body['claimedOwner'])
        self.assertEqual(body.get('internalEmail', ''), '')
        self.assertFalse(body['verifiedByOwner'])

    def test_public_list_omits_owner_private_fields(self):
        pid = self._create_provider(
            claimed_owner=True,
            internal_email='secret@example.com',
        ).json()['id']
        self._publish(pid)
        listed = self.client.get('/api/v3/marketplace/providers', **SM).json()['providers'][0]
        self.assertNotIn('claimedOwner', listed)
        self.assertNotIn('internalEmail', listed)
        self.assertNotIn('verifiedByOwner', listed)

    def test_create_with_website_and_socials(self):
        resp = self._create_provider(
            website='https://example.com',
            socials=[
                {'label': 'Instagram', 'url': 'https://instagram.com/joana'},
                {'label': 'My Blog', 'url': 'https://blog.example.com'},
            ],
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body['website'], 'https://example.com')
        self.assertEqual(len(body['socials']), 2)
        self.assertEqual(body['socials'][0]['label'], 'Instagram')

    def test_create_invalid_website(self):
        resp = self._create_provider(website='notaurl')
        self.assertEqual(resp.status_code, 400)

    def test_create_too_many_socials(self):
        socials = [
            {'label': f'Link{i}', 'url': f'https://example.com/{i}'} for i in range(11)
        ]
        resp = self._create_provider(socials=socials)
        self.assertEqual(resp.status_code, 400)

    def test_public_list_includes_website_socials(self):
        pid = self._create_provider(
            website='https://example.com',
            socials=[{'label': 'Facebook', 'url': 'https://facebook.com/page'}],
        ).json()['id']
        self._publish(pid)
        listed = self.client.get('/api/v3/marketplace/providers', **SM).json()['providers'][0]
        self.assertEqual(listed['website'], 'https://example.com')
        self.assertEqual(listed['socials'][0]['label'], 'Facebook')

    def test_patch_owner_replaces_socials(self):
        resp = self._create_provider(
            session='owner',
            socials=[{'label': 'X', 'url': 'https://x.com/old'}],
        )
        pid = resp.json()['id']
        patch = self.client.patch(
            f'/api/v3/marketplace/providers/{pid}',
            {
                'session_id': 'owner',
                'socials': [{'label': 'YouTube', 'url': 'https://youtube.com/@new'}],
            },
            format='json',
            **SM,
        )
        self.assertEqual(patch.status_code, 200)
        self.assertEqual(patch.json()['socials'][0]['label'], 'YouTube')

    def test_patch_owner_updates_internal_phone(self):
        resp = self._create_provider(session='owner', claimed_owner=True, internal_phone='+351911111111')
        pid = resp.json()['id']
        patch = self.client.patch(
            f'/api/v3/marketplace/providers/{pid}',
            {
                'session_id': 'owner',
                'internal_phone': '+351922222222',
            },
            format='json',
            **SM,
        )
        self.assertEqual(patch.status_code, 200)
        self.assertEqual(patch.json()['internalPhone'], '+351922222222')

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
