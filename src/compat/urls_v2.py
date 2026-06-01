from django.urls import path

from compat import api

urlpatterns = [
    path('stops', api.get_all_stops_v2, name='compat_v2_stops'),
    path('webapp/load', api.get_webapp_load_v2, name='compat_v2_webapp_load'),
    path('route', api.get_trip_v2, name='compat_v2_route'),
    path('like/<int:trip_id>', api.like_trip, name='compat_v2_like'),
    path('dislike/<int:trip_id>', api.dislike_trip, name='compat_v2_dislike'),
]
