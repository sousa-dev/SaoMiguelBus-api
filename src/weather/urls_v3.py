from django.urls import path

from weather.api_v3 import parish_detail_view, parish_hourly_view, parishes_list_view

urlpatterns = [
    path('parishes', parishes_list_view, name='v3-weather-parishes'),
    path('parishes/<slug:slug>/hourly', parish_hourly_view, name='v3-weather-parish-hourly'),
    path('parishes/<slug:slug>', parish_detail_view, name='v3-weather-parish-detail'),
]
