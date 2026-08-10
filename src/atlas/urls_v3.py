from django.urls import path

from atlas.api_v3 import sync_view

urlpatterns = [
    path('sync', sync_view, name='v3-atlas-sync'),
]
