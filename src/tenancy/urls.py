from django.urls import path

from marketplace.api_ops import fix_provider_phones_view
from tenancy import views

urlpatterns = [
    path(
        'celery/cancel-all',
        views.cancel_all_celery_jobs,
        name='ops_celery_cancel_all',
    ),
    path(
        'feeds/sync',
        views.trigger_feed_sync,
        name='ops_feed_sync',
    ),
    path(
        'marketplace/fix-phones',
        fix_provider_phones_view,
        name='ops_marketplace_fix_phones',
    ),
]
