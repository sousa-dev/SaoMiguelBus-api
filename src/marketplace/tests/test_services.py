"""U2 service-layer tests: CRUD, ownership, moderation, rating, search."""

from __future__ import annotations

from django.test import TestCase

from marketplace import services
from marketplace.models import Review, ServiceCategory, ServiceProvider
from tenancy.services import get_or_create_default_island


class MarketplaceServiceTests(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        self.cat = ServiceCategory.objects.create(
            island=self.island, name='Electricians', slug='electricians'
        )
        self.cat2 = ServiceCategory.objects.create(
            island=self.island, name='Plumbers', slug='plumbers'
        )
        ServiceCategory.objects.create(
            island=self.island, name='Other', slug='other'
        )

    def _create(self, session='owner', **data):
        payload = {'category_slug': 'electricians', 'name': 'Joana Electrics'}
        payload.update(data)
        return services.create_provider(island=self.island, session_hash=session, data=payload)

    # --- create / moderate --------------------------------------------------

    def test_create_provider_is_pending(self):
        result = self._create()
        provider = ServiceProvider.objects.get(id=result['id'])
        self.assertEqual(provider.status, ServiceProvider.PENDING)
        self.assertEqual(self.island_listing_count(), 0)  # not public yet

    def test_moderate_publish_makes_public(self):
        result = self._create()
        services.moderate_provider(result['id'], 'publish')
        self.assertEqual(self.island_listing_count(), 1)

    def test_create_unknown_category_raises(self):
        with self.assertRaises(services.CategoryNotFound):
            services.create_provider(
                island=self.island, session_hash='x',
                data={'category_slug': 'nope', 'name': 'X'},
            )

    def test_create_with_new_category_name(self):
        result = services.create_provider(
            island=self.island,
            session_hash='owner',
            data={'category_name': 'Dog Walking', 'name': 'Rex Walks'},
        )
        cat = ServiceCategory.objects.get(slug='dog-walking')
        self.assertTrue(cat.user_suggested)
        self.assertEqual(result['category']['slug'], 'dog-walking')

    def test_create_without_category_defaults_to_other(self):
        result = services.create_provider(
            island=self.island,
            session_hash='owner',
            data={'name': 'Generic Service'},
        )
        self.assertEqual(result['category']['slug'], 'other')

    def test_create_reuses_existing_category_by_similar_name(self):
        services.create_provider(
            island=self.island,
            session_hash='a',
            data={'category_name': 'Dog Walking', 'name': 'A'},
        )
        before = ServiceCategory.objects.filter(slug='dog-walking').count()
        services.create_provider(
            island=self.island,
            session_hash='b',
            data={'category_name': 'dog walking', 'name': 'B'},
        )
        self.assertEqual(ServiceCategory.objects.filter(slug='dog-walking').count(), before)

    def test_invalid_category_name_rejected(self):
        with self.assertRaises(services.InvalidCategoryName):
            services.create_provider(
                island=self.island,
                session_hash='x',
                data={'category_name': '!!', 'name': 'X'},
            )
        with self.assertRaises(services.InvalidCategoryName):
            services.create_provider(
                island=self.island,
                session_hash='x',
                data={'category_slug': 'electricians', 'category_name': 'Other', 'name': 'X'},
            )

    def test_moderate_invalid_action_raises(self):
        result = self._create()
        with self.assertRaises(ValueError):
            services.moderate_provider(result['id'], 'banish')

    # --- ownership ----------------------------------------------------------

    def test_update_by_non_owner_denied(self):
        result = self._create(session='owner')
        with self.assertRaises(services.OwnershipError):
            services.update_provider(
                result['id'], session_hash='intruder', is_staff=False, data={'name': 'Hijacked'}
            )

    def test_update_by_staff_allowed(self):
        result = self._create(session='owner')
        services.moderate_provider(result['id'], 'publish')
        updated = services.update_provider(
            result['id'], session_hash='', is_staff=True, data={'name': 'Staff Edit'}
        )
        self.assertEqual(updated['name'], 'Staff Edit')
        # staff edit keeps published status
        self.assertEqual(updated['status'], ServiceProvider.PUBLISHED)

    def test_owner_edit_of_published_reverts_to_pending(self):
        result = self._create(session='owner')
        services.moderate_provider(result['id'], 'publish')
        updated = services.update_provider(
            result['id'], session_hash='owner', is_staff=False, data={'bio': 'new bio'}
        )
        self.assertEqual(updated['status'], ServiceProvider.PENDING)

    # --- reviews + rating ---------------------------------------------------

    def test_review_upsert_single_row(self):
        provider = self._create()
        services.moderate_provider(provider['id'], 'publish')
        _, created1 = services.upsert_review(
            provider_id=provider['id'], session_hash='rev1', rating=5, text='great'
        )
        payload, created2 = services.upsert_review(
            provider_id=provider['id'], session_hash='rev1', rating=3, text='ok'
        )
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(Review.objects.filter(provider_id=provider['id']).count(), 1)
        self.assertEqual(payload['rating'], 3)
        self.assertEqual(payload['status'], Review.PENDING)

    def test_recompute_rating_over_published_only(self):
        provider = self._create()
        services.moderate_provider(provider['id'], 'publish')
        _, _ = services.upsert_review(provider_id=provider['id'], session_hash='a', rating=4)
        _, _ = services.upsert_review(provider_id=provider['id'], session_hash='b', rating=2)
        # pending reviews don't count
        obj = ServiceProvider.objects.get(id=provider['id'])
        self.assertEqual(obj.review_count, 0)
        # publish both
        for r in Review.objects.filter(provider_id=provider['id']):
            services.moderate_review(r.id, 'publish')
        obj.refresh_from_db()
        self.assertEqual(float(obj.rating), 3.0)
        self.assertEqual(obj.review_count, 2)

    def test_delete_review_recomputes(self):
        provider = self._create()
        services.moderate_provider(provider['id'], 'publish')
        _, _ = services.upsert_review(provider_id=provider['id'], session_hash='a', rating=4)
        review = Review.objects.get(provider_id=provider['id'])
        services.moderate_review(review.id, 'publish')
        services.delete_review(review.id, session_hash='a', is_staff=False)
        obj = ServiceProvider.objects.get(id=provider['id'])
        self.assertEqual(obj.review_count, 0)
        self.assertEqual(float(obj.rating), 0.0)

    # --- visibility / search ------------------------------------------------

    def test_list_excludes_non_published(self):
        self._create(session='a')  # pending
        pub = self._create(session='b', name='Published Co')
        services.moderate_provider(pub['id'], 'publish')
        names = [p['name'] for p in services.list_providers()]
        self.assertEqual(names, ['Published Co'])

    def test_get_provider_pending_only_owner_or_staff(self):
        result = self._create(session='owner')
        self.assertIsNone(services.get_provider(result['id'], viewer_session_hash='other'))
        self.assertIsNotNone(services.get_provider(result['id'], viewer_session_hash='owner'))
        self.assertIsNotNone(services.get_provider(result['id'], is_staff=True))

    def test_search_and_category_filter(self):
        a = self._create(session='a', name='Spark Electric', bio='wiring expert')
        b = services.create_provider(
            island=self.island, session_hash='b',
            data={'category_slug': 'plumbers', 'name': 'Drips Plumbing', 'bio': 'pipes'},
        )
        for r in (a, b):
            services.moderate_provider(r['id'], 'publish')
        self.assertEqual([p['name'] for p in services.list_providers(q='wiring')], ['Spark Electric'])
        self.assertEqual([p['name'] for p in services.list_providers(category='plumbers')], ['Drips Plumbing'])

    def test_proximity_orders_nearest_first(self):
        near = self._create(session='a', name='Near', latitude=37.74, longitude=-25.67)
        far = self._create(session='b', name='Far', latitude=38.5, longitude=-28.2)
        for r in (near, far):
            services.moderate_provider(r['id'], 'publish')
        ordered = services.list_providers(lat=37.74, lng=-25.67)
        self.assertEqual([p['name'] for p in ordered], ['Near', 'Far'])

    def test_soft_delete_excludes_from_list(self):
        result = self._create(session='owner', name='Gone')
        services.moderate_provider(result['id'], 'publish')
        services.soft_delete_provider(result['id'], session_hash='owner', is_staff=False)
        self.assertEqual(self.island_listing_count(), 0)
        self.assertIsNone(services.get_provider(result['id'], is_staff=True))

    def test_update_review_owner_and_denials(self):
        provider = self._create()
        services.moderate_provider(provider['id'], 'publish')
        services.upsert_review(provider_id=provider['id'], session_hash='rev', rating=5, text='a')
        review = Review.objects.get(provider_id=provider['id'])
        services.moderate_review(review.id, 'publish')
        # owner edit reverts to pending + recomputes (no published reviews now)
        updated = services.update_review(
            review.id, session_hash='rev', is_staff=False, data={'rating': 2, 'text': 'meh'}
        )
        self.assertEqual(updated['rating'], 2)
        self.assertEqual(updated['status'], Review.PENDING)
        # non-owner denied
        with self.assertRaises(services.OwnershipError):
            services.update_review(review.id, session_hash='other', is_staff=False, data={'rating': 1})
        with self.assertRaises(services.OwnershipError):
            services.delete_review(review.id, session_hash='other', is_staff=False)

    def test_list_reviews_published_only(self):
        provider = self._create()
        services.moderate_provider(provider['id'], 'publish')
        services.upsert_review(provider_id=provider['id'], session_hash='a', rating=5)
        self.assertEqual(services.list_reviews(provider['id']), [])  # pending hidden
        review = Review.objects.get(provider_id=provider['id'])
        services.moderate_review(review.id, 'publish')
        self.assertEqual(len(services.list_reviews(provider['id'])), 1)

    def test_not_found_paths_return_none(self):
        self.assertIsNone(services.get_provider(99999))
        self.assertIsNone(services.update_provider(99999, session_hash='x', is_staff=False, data={}))
        self.assertIsNone(services.soft_delete_provider(99999, session_hash='x', is_staff=False))
        self.assertIsNone(services.moderate_provider(99999, 'publish'))
        self.assertIsNone(services.upsert_review(provider_id=99999, session_hash='x', rating=5))
        self.assertIsNone(services.update_review(99999, session_hash='x', is_staff=False, data={}))
        self.assertIsNone(services.delete_review(99999, session_hash='x', is_staff=False))
        self.assertIsNone(services.moderate_review(99999, 'publish'))

    # --- helpers ------------------------------------------------------------

    def island_listing_count(self) -> int:
        return len(services.list_providers())
