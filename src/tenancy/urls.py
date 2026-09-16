from django.urls import path

from azoresbus.api_ops import azoresbus_snapshot_view, azoresbus_trigger_sync_view
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
    path(
        'azoresbus/snapshot',
        azoresbus_snapshot_view,
        name='ops_azoresbus_snapshot',
    ),
    path(
        'azoresbus/sync',
        azoresbus_trigger_sync_view,
        name='ops_azoresbus_sync',
    ),
]
