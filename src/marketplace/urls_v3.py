"""Marketplace v3 URL routes."""

from __future__ import annotations

from django.urls import path

from marketplace.api_admin import (
    admin_categories_view,
    admin_category_detail_view,
    admin_provider_detail_view,
    admin_provider_moderate_view,
    admin_providers_view,
    admin_queue_view,
    admin_review_detail_view,
    admin_review_moderate_view,
    admin_reviews_view,
)
from marketplace.api_v3 import (
    categories_view,
    provider_detail_view,
    provider_moderate_view,
    provider_reviews_view,
    providers_view,
    review_detail_view,
    review_moderate_view,
)

urlpatterns = [
    path('admin/queue', admin_queue_view, name='v3-marketplace-admin-queue'),
    path('admin/providers', admin_providers_view, name='v3-marketplace-admin-providers'),
    path(
        'admin/providers/<int:provider_id>',
        admin_provider_detail_view,
        name='v3-marketplace-admin-provider-detail',
    ),
    path(
        'admin/providers/<int:provider_id>/moderate',
        admin_provider_moderate_view,
        name='v3-marketplace-admin-provider-moderate',
    ),
    path('admin/reviews', admin_reviews_view, name='v3-marketplace-admin-reviews'),
    path(
        'admin/reviews/<int:review_id>',
        admin_review_detail_view,
        name='v3-marketplace-admin-review-detail',
    ),
    path(
        'admin/reviews/<int:review_id>/moderate',
        admin_review_moderate_view,
        name='v3-marketplace-admin-review-moderate',
    ),
    path('admin/categories', admin_categories_view, name='v3-marketplace-admin-categories'),
    path(
        'admin/categories/<int:category_id>',
        admin_category_detail_view,
        name='v3-marketplace-admin-category-detail',
    ),
    path('categories', categories_view, name='v3-marketplace-categories'),
    path('providers', providers_view, name='v3-marketplace-providers'),
    path('providers/<int:provider_id>', provider_detail_view, name='v3-marketplace-provider-detail'),
    path('providers/<int:provider_id>/reviews', provider_reviews_view, name='v3-marketplace-provider-reviews'),
    path('providers/<int:provider_id>/moderate', provider_moderate_view, name='v3-marketplace-provider-moderate'),
    path('reviews/<int:review_id>', review_detail_view, name='v3-marketplace-review-detail'),
    path('reviews/<int:review_id>/moderate', review_moderate_view, name='v3-marketplace-review-moderate'),
]
