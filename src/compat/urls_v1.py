from django.urls import path

from compat import api

urlpatterns = [
    path('stops', api.get_all_stops_v1, name='compat_v1_stops'),
    path('route', api.get_trip_v1, name='compat_v1_route'),
    path('gmaps', api.get_gmaps_v1, name='compat_v1_gmaps'),
    path('stat', api.add_stat_v1, name='compat_v1_stat'),
    path('ad', api.get_ad_v1, name='compat_v1_ad'),
    path('ad/click', api.click_ad_v1, name='compat_v1_ad_click'),
    path('subscription/verify/', api.verify_subscription_view, name='compat_v1_subscription_verify'),
]
