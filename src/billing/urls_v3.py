from django.urls import path

from billing import api_v3

urlpatterns = [
    path('entitlement', api_v3.entitlement_view, name='v3-billing-entitlement'),
    path('webhooks/revenuecat', api_v3.revenuecat_webhook, name='v3-billing-revenuecat-webhook'),
]
