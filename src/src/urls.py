"""src URL Configuration."""

from django.contrib import admin
from django.urls import include, path
from django.conf import settings

urlpatterns = [
    path('dashboard/admin/', admin.site.urls),
    path('api/v1/', include('compat.urls_v1')),
    path('api/v2/', include('compat.urls_v2')),
]

if 'legal' in settings.INSTALLED_APPS:
    urlpatterns.append(path('legal/', include('legal.urls')))

if 'stripe_payments' in settings.INSTALLED_APPS:
    urlpatterns.append(path('payment/', include('stripe_payments.urls')))

if 'user_management' in settings.INSTALLED_APPS:
    urlpatterns.append(path('', include('user_management.urls')))

if 'allauth' in settings.INSTALLED_APPS:
    urlpatterns.append(path('accounts/', include('allauth.urls')))
