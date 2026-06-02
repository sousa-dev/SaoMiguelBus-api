from django.urls import path

from consent.api import consent_view

urlpatterns = [
    path('', consent_view, name='v3-consent'),
]
