"""src URL Configuration."""

from django.contrib import admin
from django.urls import include, path
from django.conf import settings

from tenancy.api_v3 import bootstrap_view

urlpatterns = [
    path('dashboard/admin/', admin.site.urls),
    path('api/v1/', include('compat.urls_v1')),
    path('api/v2/', include('compat.urls_v2')),
    path('api/v1/ops/', include('tenancy.urls')),
    path('api/v3/bootstrap', bootstrap_view),
    path('api/v3/consent/', include('consent.urls')),
    path('api/v3/privacy/', include('consent.urls_privacy')),
    path('api/v3/analytics/', include('analytics.urls_v3')),
    path('api/v3/transit/', include('transit.urls_v3')),
    path('api/v3/news/', include('news.urls_v3')),
]

if 'legal' in settings.INSTALLED_APPS:
    urlpatterns.append(path('legal/', include('legal.urls')))

if 'stripe_payments' in settings.INSTALLED_APPS:
    urlpatterns.append(path('payment/', include('stripe_payments.urls')))

if 'user_management' in settings.INSTALLED_APPS:
    urlpatterns.append(path('', include('user_management.urls')))

if 'allauth' in settings.INSTALLED_APPS:
    urlpatterns.append(path('accounts/', include('allauth.urls')))
