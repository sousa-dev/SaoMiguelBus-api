from django.urls import path

from events.api_v3 import tour_detail_view, tours_list_view

urlpatterns = [
    path('tours', tours_list_view, name='v3-events-tours'),
    path('tours/<str:product_code>', tour_detail_view, name='v3-events-tour-detail'),
]
