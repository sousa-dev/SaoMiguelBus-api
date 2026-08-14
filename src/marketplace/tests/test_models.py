"""U1 model-level tests: defaults, ownership, uniqueness, moderation status."""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import TestCase

from marketplace.models import Review, ServiceCategory, ServiceProvider
from tenancy.services import get_or_create_default_island


class MarketplaceModelTests(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()
        # marketplace/0002 seeds eight default categories for sao-miguel.
        # It only ever looked like a no-op because the migration graph used
        # to order it BEFORE the island existed; these fixtures build their
        # own categories and must not depend on that accident.
        ServiceCategory.objects.filter(island=self.island).delete()
        self.category = ServiceCategory.objects.create(
            island=self.island, name='Electricians', slug='electricians'
        )

    def _provider(self, **kwargs):
        defaults = dict(
            island=self.island,
            name='Joana Electrics',
            category=self.category,
            created_by_session_hash='sess-a',
        )
        defaults.update(kwargs)
        return ServiceProvider.objects.create(**defaults)

    def test_provider_defaults(self):
        provider = self._provider()
        self.assertEqual(provider.status, ServiceProvider.PENDING)
        self.assertEqual(provider.rating, 0)
        self.assertEqual(provider.review_count, 0)
        self.assertFalse(provider.is_promoted)

    def test_is_owned_by(self):
        provider = self._provider(created_by_session_hash='owner-hash')
        self.assertTrue(provider.is_owned_by('owner-hash'))
        self.assertFalse(provider.is_owned_by('other-hash'))
        self.assertFalse(provider.is_owned_by(''))

    def test_category_unique_per_island(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ServiceCategory.objects.create(
                    island=self.island, name='Electricians 2', slug='electricians'
                )

    def test_review_unique_per_session_per_provider(self):
        provider = self._provider()
        Review.objects.create(
            island=self.island, provider=provider, rating=5,
            created_by_session_hash='sess-x',
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Review.objects.create(
                    island=self.island, provider=provider, rating=1,
                    created_by_session_hash='sess-x',
                )

    def test_published_filter_excludes_non_published(self):
        self._provider(name='pending one', status=ServiceProvider.PENDING)
        self._provider(name='published one', status=ServiceProvider.PUBLISHED,
                       created_by_session_hash='sess-b')
        published = ServiceProvider.objects.for_island(self.island).filter(
            status=ServiceProvider.PUBLISHED
        )
        self.assertEqual([p.name for p in published], ['published one'])
