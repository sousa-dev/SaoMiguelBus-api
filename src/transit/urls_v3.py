from django.urls import path

from transit.api_v3 import transit_search_view, transit_stops_view, transit_trip_vote_view

urlpatterns = [
    path('stops', transit_stops_view, name='v3-transit-stops'),
    path('search', transit_search_view, name='v3-transit-search'),
    path('trips/<int:trip_id>/vote', transit_trip_vote_view, name='v3-transit-trip-vote'),
]
