from django.urls import path

from trails.api_v3 import trail_detail_view, trails_list_view, trails_pois_view

urlpatterns = [
    path('pois', trails_pois_view, name='v3-trails-pois'),
    path('', trails_list_view, name='v3-trails-list'),
    path('<int:trail_id>', trail_detail_view, name='v3-trail-detail'),
]
