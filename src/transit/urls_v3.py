from django.urls import path

from transit.api_v3 import (
    transit_directions_view,
    transit_line_detail_view,
    transit_offline_bundle_view,
    transit_offline_version_view,
    transit_route_weather_view,
    transit_search_view,
    transit_stops_view,
    transit_tariffs_view,
    transit_trip_detail_view,
    transit_trip_vote_view,
)

urlpatterns = [
    path('stops', transit_stops_view, name='v3-transit-stops'),
    path('offline-bundle', transit_offline_bundle_view, name='v3-transit-offline-bundle'),
    path('offline-bundle/version', transit_offline_version_view, name='v3-transit-offline-version'),
    path('search', transit_search_view, name='v3-transit-search'),
    path('tariffs', transit_tariffs_view, name='transit-tariffs-v3'),
    path('route-weather', transit_route_weather_view, name='v3-transit-route-weather'),
    path('directions', transit_directions_view, name='v3-transit-directions'),
    path('trips/<int:trip_id>', transit_trip_detail_view, name='v3-transit-trip-detail'),
    path('trips/<int:trip_id>/vote', transit_trip_vote_view, name='v3-transit-trip-vote'),
    path('lines/<str:line_code>', transit_line_detail_view, name='v3-transit-line-detail'),
]
