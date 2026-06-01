from django.urls import path

from compat import api

urlpatterns = [
    path('stops', api.get_all_stops_v2, name='compat_v2_stops'),
    path('webapp/load', api.get_webapp_load_v2, name='compat_v2_webapp_load'),
]
