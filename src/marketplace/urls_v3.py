"""Marketplace v3 URL routes."""

from __future__ import annotations

from django.urls import path

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
    path('categories', categories_view, name='v3-marketplace-categories'),
    path('providers', providers_view, name='v3-marketplace-providers'),
    path('providers/<int:provider_id>', provider_detail_view, name='v3-marketplace-provider-detail'),
    path('providers/<int:provider_id>/reviews', provider_reviews_view, name='v3-marketplace-provider-reviews'),
    path('providers/<int:provider_id>/moderate', provider_moderate_view, name='v3-marketplace-provider-moderate'),
    path('reviews/<int:review_id>', review_detail_view, name='v3-marketplace-review-detail'),
    path('reviews/<int:review_id>/moderate', review_moderate_view, name='v3-marketplace-review-moderate'),
]
