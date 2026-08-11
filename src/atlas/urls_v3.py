from django.urls import path

from atlas.api_v3 import stats_view, sync_view

urlpatterns = [
    path('stats', stats_view, name='v3-atlas-stats'),
    path('sync', sync_view, name='v3-atlas-sync'),
]
